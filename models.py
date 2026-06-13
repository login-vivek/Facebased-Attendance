import torch
import torch.nn as nn
import torch.nn.functional as F
from facenet_pytorch import InceptionResnetV1

class SelfAttention(nn.Module):
    def __init__(self, embed_size, heads):
        super(SelfAttention, self).__init__()
        self.embed_size = embed_size
        self.heads = heads
        self.head_dim = embed_size // heads

        assert (
            self.head_dim * heads == embed_size
        ), "Embed size needs to be divisible by heads"

        self.values = nn.Linear(self.head_dim, self.head_dim, bias=False)
        self.keys = nn.Linear(self.head_dim, self.head_dim, bias=False)
        self.queries = nn.Linear(self.head_dim, self.head_dim, bias=False)
        self.fc_out = nn.Linear(heads * self.head_dim, embed_size)

    def forward(self, values, keys, query):
        N = query.shape[0]
        value_len, key_len, query_len = values.shape[1], keys.shape[1], query.shape[1]

        # Split the embedding into self.heads pieces
        values = values.reshape(N, value_len, self.heads, self.head_dim)
        keys = keys.reshape(N, key_len, self.heads, self.head_dim)
        queries = query.reshape(N, query_len, self.heads, self.head_dim)

        values = self.values(values)
        keys = self.keys(keys)
        queries = self.queries(queries)

        # Einsum does matrix multiplication for query * key.T
        # sum over last two dimensions (head_dim)
        attention = torch.einsum("nqhd,nkhd->nhqk", [queries, keys])
        # queries: (N, query_len, heads, head_dim)
        # keys: (N, key_len, heads, head_dim)
        # attention: (N, heads, query_len, key_len)

        attention_weights = F.softmax(attention / (self.embed_size ** (1 / 2)), dim=3)

        out = torch.einsum("nhql,nlhd->nqhd", [attention_weights, values]).reshape(
            N, query_len, self.heads * self.head_dim
        )
        # attention_weights: (N, heads, query_len, key_len)
        # values: (N, value_len, heads, head_dim)
        # out: (N, query_len, heads * head_dim)

        out = self.fc_out(out)
        return out


class EnhancedSiameseNetwork(nn.Module):
    def __init__(self, embedding_dim=512):
        super(EnhancedSiameseNetwork, self).__init__()
        # Base model with pretrained weights
        self.base_model = InceptionResnetV1(pretrained='vggface2').eval()

        # Freeze initial layers to prevent overfitting
        for param in list(self.base_model.parameters())[:-8]:  # Freeze all but last few layers
            param.requires_grad = False

        # Enhanced feature extraction and embedding layers
        self.conv1 = nn.Conv2d(512, 512, kernel_size=1, stride=1, padding=0)
        self.bn1 = nn.BatchNorm2d(512)
        self.attention = SelfAttention(512, heads=8) # Added heads argument

        # Fully connected layers for embedding
        self.fc1 = nn.Linear(512, 512)
        self.fc2 = nn.Linear(512, 512)
        self.embedding_layer = nn.Linear(512, embedding_dim)

        # Normalization and activation
        self.batch_norm = nn.BatchNorm1d(512)
        self.dropout = nn.Dropout(p=0.3)
        self.relu = nn.ReLU()

    def forward(self, x):
        # Get features from base model
        x = self.base_model(x) # Output of InceptionResnetV1 is typically 512-dim embedding

        # Additional processing layers as per your snippet
        x = self.fc1(x)
        x = self.relu(x)
        x = self.batch_norm(x)
        x = self.dropout(x)
        x = self.fc2(x)
        x = self.relu(x)

        # Final embedding with L2 normalization
        x = self.embedding_layer(x)
        x = F.normalize(x, p=2, dim=1)  # L2 normalization for better similarity metrics

        return x