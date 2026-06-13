import os
import torch
import numpy as np
import pickle
import pandas as pd
from PIL import Image
from torchvision import transforms
from tqdm import tqdm
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from config import Config
from models import EnhancedSiameseNetwork

# Device global variable from Config
DEVICE = Config.DEVICE

# Dataset class for Siamese Network training
class SiameseDataset(Dataset):
    def __init__(self, df, transform=None):
        self.df = df
        self.labels = df['label'].unique()
        self.transform = transform
        self.label_to_paths = {label: list(df[df['label'] == label]['image_path']) for label in self.labels}

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        anchor_path = self.df.iloc[idx]['image_path']
        anchor_label = self.df.iloc[idx]['label']

        # Get positive sample (same label)
        positive_paths = [p for p in self.label_to_paths[anchor_label] if p != anchor_path]
        if not positive_paths: # Handle case with only one image for a label
            positive_path = anchor_path # Use anchor as positive if no other available
        else:
            positive_path = np.random.choice(positive_paths)

        # Get negative sample (different label)
        negative_label = np.random.choice([l for l in self.labels if l != anchor_label])
        negative_path = np.random.choice(self.label_to_paths[negative_label])

        # Load images
        anchor_img = Image.open(anchor_path).convert('RGB')
        positive_img = Image.open(positive_path).convert('RGB')
        negative_img = Image.open(negative_path).convert('RGB')

        if self.transform:
            anchor_img = self.transform(anchor_img)
            positive_img = self.transform(positive_img)
            negative_img = self.transform(negative_img)

        return anchor_img, positive_img, negative_img


def augment_faces(face_data, classroom_id):
    """
    Augments face images with various transformations.
    `face_data` is expected to be a list of dicts: `[{'image_path': '...', 'label': '...'}]`
    """
    print(f"Augmenting faces for classroom {classroom_id}...")
    augmented_path_data = []
    
    # Specific directory for augmented images for this classroom
    augmentation_output_dir = os.path.join(Config.DATASETS_FOLDER, classroom_id, "augmented")
    os.makedirs(augmentation_output_dir, exist_ok=True)

    augment_transforms = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1),
        transforms.RandomPerspective(distortion_scale=0.1, p=0.5),
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)), # Assuming input size for model is 224x224
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
    ])

    for face_info in tqdm(face_data, desc="Augmenting"):
        original_img_path = face_info['image_path']
        label = face_info['label']

        try:
            face_img = Image.open(original_img_path).convert('RGB')
        except FileNotFoundError:
            print(f"Warning: Original face image not found for augmentation: {original_img_path}")
            continue

        num_augmentations = 5 # Generate 5 augmented images per original face

        for i in range(num_augmentations):
            augmented_face_tensor = augment_transforms(face_img)
            # Convert tensor back to PIL Image (denormalize first for correct visual representation)
            augmented_face_pil_save = transforms.ToPILImage()(augmented_face_tensor * 0.5 + 0.5)

            aug_filename = f"{label}_aug_{i}.jpg"
            aug_path = os.path.join(augmentation_output_dir, aug_filename)
            augmented_face_pil_save.save(aug_path)
            augmented_path_data.append({'image_path': aug_path, 'label': label})

    print(f"Augmented images saved to {augmentation_output_dir}")
    return augmented_path_data


def train_siamese_network_for_classroom(classroom_id, num_epochs=20, batch_size=32):
    """
    Trains the EnhancedSiameseNetwork for a specific classroom.
    Collects all labeled face images (original + augmented) for training.
    """
    print(f"Initiating training for classroom {classroom_id}...")

    # Load all labeled faces for this classroom
    labeled_faces_dir = os.path.join(Config.DATASETS_FOLDER, classroom_id, "labeled_faces")
    augmented_faces_dir = os.path.join(Config.DATASETS_FOLDER, classroom_id, "augmented")

    all_paths = []
    if os.path.exists(labeled_faces_dir):
        for filename in os.listdir(labeled_faces_dir):
            if filename.lower().endswith(Config.ALLOWED_EXTENSIONS):
                label = os.path.splitext(filename)[0] # e.g., "Roll_001"
                all_paths.append({'image_path': os.path.join(labeled_faces_dir, filename), 'label': label})
    
    if os.path.exists(augmented_faces_dir):
        for filename in os.listdir(augmented_faces_dir):
            if filename.lower().endswith(Config.ALLOWED_EXTENSIONS):
                # Labels for augmented images are often like "Roll_001_aug_0.jpg"
                label = os.path.splitext(filename)[0].rsplit('_aug', 1)[0] # Extract "Roll_001"
                all_paths.append({'image_path': os.path.join(augmented_faces_dir, filename), 'label': label})

    if not all_paths:
        raise ValueError(f"No labeled or augmented face data found for classroom {classroom_id}. Please assign roll numbers first.")

    path_df = pd.DataFrame(all_paths)

    if len(path_df['label'].unique()) < 2:
        raise ValueError("Need at least two distinct individuals (labels) for Siamese network training.")

    # Define transforms for training
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
    ])

    dataset = SiameseDataset(path_df, transform=transform)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers= 0)

    model = EnhancedSiameseNetwork().to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.0005) # Slightly reduced learning rate
    criterion = nn.TripletMarginLoss(margin=0.8) # Adjusted margin for potentially better separation

    model.train()
    print(f"Starting training for {num_epochs} epochs...")
    for epoch in range(num_epochs):
        total_loss = 0
        pbar = tqdm(dataloader, desc=f"Epoch {epoch+1}/{num_epochs}")
        for anchor, positive, negative in pbar:
            anchor, positive, negative = anchor.to(DEVICE), positive.to(DEVICE), negative.to(DEVICE)

            optimizer.zero_grad()

            anchor_out = model(anchor)
            positive_out = model(positive)
            negative_out = model(negative)

            loss = criterion(anchor_out, positive_out, negative_out)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            pbar.set_postfix(loss=total_loss / (pbar.n + 1)) # Update postfix for average loss

        avg_loss = total_loss / len(dataloader)
        print(f"Epoch {epoch+1} finished. Average Loss: {avg_loss:.4f}")

    # Save the trained model
    model_save_dir = os.path.join(Config.MODELS_FOLDER, classroom_id)
    os.makedirs(model_save_dir, exist_ok=True)
    model_path = os.path.join(model_save_dir, 'siamese_model_best.pth')
    torch.save(model.state_dict(), model_path)
    print(f"Model saved to {model_path}")

    # Generate and save embeddings
    embedding_dict, label_embeddings = generate_embeddings(model, path_df, transform, classroom_id)
    embeddings_save_dir = os.path.join(Config.EMBEDDINGS_FOLDER, classroom_id)
    os.makedirs(embeddings_save_dir, exist_ok=True)
    embedding_dict_path = os.path.join(embeddings_save_dir, 'embedding_dict.pkl')
    label_embeddings_path = os.path.join(embeddings_save_dir, 'label_embeddings.pkl')
    
    with open(embedding_dict_path, 'wb') as f:
        pickle.dump(embedding_dict, f)
    with open(label_embeddings_path, 'wb') as f:
        pickle.dump(label_embeddings, f)
    print(f"Embeddings saved to {embeddings_save_dir}")

    return {"status": "success", "message": "Training complete.", "model_path": model_path}


def generate_embeddings(model, path_df, transform, classroom_id):
    """
    Generates and saves embeddings for all faces in the dataset for a given classroom.
    This function should be called after the model is trained.
    """
    print(f"Generating embeddings for classroom {classroom_id}...")
    embedding_dict = {} # Stores average embedding per label (e.g., Roll_001)
    label_embeddings = {} # Stores all individual embeddings per label (for ensemble)

    model.eval()
    with torch.no_grad():
        for _, row in tqdm(path_df.iterrows(), total=len(path_df), desc="Generating Embeddings"):
            img_path = row['image_path']
            label = row['label']

            try:
                img = Image.open(img_path).convert('RGB')
                img_tensor = transform(img).unsqueeze(0).to(DEVICE)
                embedding = model(img_tensor).squeeze().cpu().numpy()
                embedding = embedding / np.linalg.norm(embedding) # L2 Normalize

                if label not in label_embeddings:
                    label_embeddings[label] = []
                label_embeddings[label].append(embedding)

            except Exception as e:
                print(f"Error processing {img_path} for embedding: {e}")

    # Compute average embeddings
    for label, embeddings_list in label_embeddings.items():
        if embeddings_list:
            # Average and then L2 normalize the average
            avg_emb = np.mean(embeddings_list, axis=0)
            embedding_dict[label] = avg_emb / np.linalg.norm(avg_emb) if np.linalg.norm(avg_emb) > 0 else avg_emb
            
    print(f"Generated embeddings for {len(embedding_dict)} unique labels.")
    return embedding_dict, label_embeddings