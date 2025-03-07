import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Sequential, Linear, ReLU
from torch_geometric.nn import GATConv
from torch_geometric.nn import global_max_pool as gmp
import torch
from transformers import BertModel, BertTokenizer
# from torch.nn import GATConv
# from torch.nn import global_max_pool as gmp
import torch
from transformers import AutoTokenizer, AutoModel



# GAT  model
class GATNet(torch.nn.Module):
    def __init__(self, num_features_xd=78, n_output=1, num_features_xt=25,
                     n_filters=32, embed_dim=128, output_dim=128, dropout=0.2):
        super(GATNet, self).__init__()

        # graph layers
        self.gcn1 = GATConv(num_features_xd, num_features_xd, heads=10, dropout=dropout)
        self.gcn2 = GATConv(num_features_xd * 10, output_dim, dropout=dropout)
        self.fc_g1 = nn.Linear(output_dim, output_dim)

        
        # bert layers:
       




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
        # 1D convolution on protein sequence
        self.embedding_xt = nn.Embedding(num_features_xt + 1, embed_dim)
        self.conv_xt1 = nn.Conv1d(in_channels=1000, out_channels=n_filters, kernel_size=8)
        self.fc_xt1 = nn.Linear(32*121, output_dim)

        # combined layers
        self.fc1 = nn.Linear(256, 1024)
        self.fc2 = nn.Linear(1024, 256)
        self.out = nn.Linear(256, n_output)

        # activation and regularization
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, data):
        


        # protein input feed-forward:
        target = data.target
        embedded_xt = self.embedding_xt(target)
        conv_xt = self.conv_xt1(embedded_xt)
        conv_xt = self.relu(conv_xt)

        # flatten
        xt = conv_xt.view(-1, 32 * 121)
        xt = self.fc_xt1(xt)
        

        # k_bert
        smiles = data.smiles
        # print(len(smiles))
        # print(len(smiles[0]))
        max_length = 128  # 每个SMILES字符串的最大长度
        input_ids = []
        for s in smiles:
            s = s[0]
            tokens = self.tokenizer.tokenize(s)[:max_length-2]
            tokens = ['[CLS]'] + tokens + ['[SEP]']
            ids = self.tokenizer.convert_tokens_to_ids(tokens)
            padding = [0] * (max_length - len(ids))
            ids += padding
            input_ids.append(ids)
        device = torch.device('cuda')
        input_ids = torch.tensor(input_ids).to(device)
        print()
        # 将BERT输入传递给BERT模型，以获得向量表示
        # outputs = self.k_bert[input_ids]
        outputs = self.k_bert(input_ids)
        last_hidden_states = outputs[0]
        smiles_embeddings = torch.mean(last_hidden_states, dim=1).squeeze()
        
        # graph input feed-forward
        x, edge_index, batch = data.x, data.edge_index, data.batch

        x = F.dropout(x, p=0.2, training=self.training)
        x = F.elu(self.gcn1(x, edge_index))
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.gcn2(x, edge_index)
        x = self.relu(x)
        x = gmp(x, batch)          # global max pooling
        x = self.fc_g1(x)
        x = self.relu(x)
        
        
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
