import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Sequential, Linear, ReLU
from torch_geometric.nn import GINConv, global_add_pool
from transformers import BertModel, BertTokenizer
from torch_geometric.nn import global_mean_pool as gap, global_max_pool as gmp
# from torch.nn import GINConv, global_add_pool
# from torch.nn import global_mean_pool as gap, global_max_pool as gmp

# GINConv model
class GINConvNet(torch.nn.Module):
    def __init__(self, n_output=1,num_features_xd=78, num_features_xt=25,
                 n_filters=32, embed_dim=128, output_dim=128, dropout=0.2):

        super(GINConvNet, self).__init__()

        dim = 32
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU()
        self.n_output = n_output
        # convolution layers
        nn1 = Sequential(Linear(num_features_xd, dim), ReLU(), Linear(dim, dim))
        self.conv1 = GINConv(nn1)
        self.bn1 = torch.nn.BatchNorm1d(dim)

        nn2 = Sequential(Linear(dim, dim), ReLU(), Linear(dim, dim))
        self.conv2 = GINConv(nn2)
        self.bn2 = torch.nn.BatchNorm1d(dim)

        nn3 = Sequential(Linear(dim, dim), ReLU(), Linear(dim, dim))
        self.conv3 = GINConv(nn3)
        self.bn3 = torch.nn.BatchNorm1d(dim)

        nn4 = Sequential(Linear(dim, dim), ReLU(), Linear(dim, dim))
        self.conv4 = GINConv(nn4)
        self.bn4 = torch.nn.BatchNorm1d(dim)

        nn5 = Sequential(Linear(dim, dim), ReLU(), Linear(dim, dim))
        self.conv5 = GINConv(nn5)
        self.bn5 = torch.nn.BatchNorm1d(dim)

        self.fc1_xd = Linear(dim, output_dim)

        # 1D convolution on protein sequence
        self.embedding_xt = nn.Embedding(num_features_xt + 1, embed_dim)
        self.conv_xt_1 = nn.Conv1d(in_channels=1000, out_channels=n_filters, kernel_size=8)
        self.fc1_xt = nn.Linear(32*121, output_dim)

        # combined layers
        self.fc1 = nn.Linear(568, 1024)
        self.fc2 = nn.Linear(1024, 256)
        self.out = nn.Linear(256, self.n_output)        # n_output = 1 for regression task

        # 加载预训练好的BERT模型和tokenizer
        # 普通bert
        # self.k_bert = BertModel.from_pretrained('bert-base-uncased')
        from transformers import DistilBertTokenizer, DistilBertModel
        # model_name = '/distilbert-base-uncased'
        model_name = 'huawei-noah/TinyBERT_General_4L_312D'
        # self.k_bert = DistilBertModel.from_pretrained("distilbert-base-uncased")
        self.k_bert = BertModel.from_pretrained(model_name)
        #k-bert
        # model_path = './models/k_bert.pth'
        # self.k_bert = torch.load(model_path)
        # self.tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
        self.tokenizer = BertTokenizer.from_pretrained(model_name)

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        target = data.target

        x = F.relu(self.conv1(x, edge_index))
        x = self.bn1(x)
        x = F.relu(self.conv2(x, edge_index))
        x = self.bn2(x)
        x = F.relu(self.conv3(x, edge_index))
        x = self.bn3(x)
        x = F.relu(self.conv4(x, edge_index))
        x = self.bn4(x)
        x = F.relu(self.conv5(x, edge_index))
        x = self.bn5(x)
        x = global_add_pool(x, batch)
        x = F.relu(self.fc1_xd(x))
        x = F.dropout(x, p=0.2, training=self.training)

        embedded_xt = self.embedding_xt(target)
        conv_xt = self.conv_xt_1(embedded_xt)
        # flatten
        xt = conv_xt.view(-1, 32 * 121)
        xt = self.fc1_xt(xt)

        # k_bert
        smiles = data.smiles
        # print(len(smiles))
        # print(len(smiles[0]))
        max_length = 128  # 每个SMILES字符串的最大长度
        input_ids = []
        for s in smiles:
            s = s[0]
            tokens = self.tokenizer.tokenize(s)[:max_length - 2]
            tokens = ['[CLS]'] + tokens + ['[SEP]']
            ids = self.tokenizer.convert_tokens_to_ids(tokens)
            padding = [0] * (max_length - len(ids))
            ids += padding
            input_ids.append(ids)
        device = torch.device('cuda')
        input_ids = torch.tensor(input_ids).to(device)
        # print()
        # 将BERT输入传递给BERT模型，以获得向量表示
        # outputs = self.k_bert[input_ids]
        outputs = self.k_bert(input_ids)
        last_hidden_states = outputs[0]
        smiles_embeddings = torch.mean(last_hidden_states, dim=1).squeeze()

        # concat
        xc = torch.cat((x, xt, smiles_embeddings), 1)
        # add some dense layers
        xc = self.fc1(xc)
        xc = self.relu(xc)
        xc = self.dropout(xc)
        xc = self.fc2(xc)
        xc = self.relu(xc)
        xc = self.dropout(xc)
        out = self.out(xc)
        return out
