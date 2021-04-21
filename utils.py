import numpy as np
import pandas as pd
import csv
import networkx as nx
import scipy.sparse as sp
import h5py
import torch
from torch.utils.data import Dataset

# 功能：按行标准化稀疏矩阵
# 输入：普通sp.coo_matrix
# 输出：行标准化sp.coo_matrix
def normalize(mx):
    rowsum = np.array(mx.sum(1))
    r_inv = np.power(rowsum, -1).flatten()
    r_inv[np.isinf(r_inv)] = 0.
    r_mat_inv = sp.diags(r_inv)
    mx = r_mat_inv.dot(mx)
    return mx

# 功能：coo稀疏矩阵到稀疏张量
# 输入：sp.coo_matrix
# 输出：torch sparse tensor
def sparse_mx_to_torch_sparse_tensor(sparse_mx):
    """Convert a scipy sparse matrix to a torch sparse tensor."""
    sparse_mx = sparse_mx.tocoo().astype(np.float32)
    indices = torch.from_numpy(
        np.vstack((sparse_mx.row, sparse_mx.col)).astype(np.int64))
    values = torch.from_numpy(sparse_mx.data)
    shape = torch.Size(sparse_mx.shape)
    return torch.sparse.FloatTensor(indices, values, shape)

# 功能：加载degelist格式的graph
# 输入：图的名字，如'bio72'，'dpwk'
# 输出：coo矩阵，csr矩阵，adj矩阵
def load_edgelist_graph( name ):
    path = './graphs/' + name + '.edgelist'
    num_of_nodes = 25023           
    idx = np.array([i for i in range(num_of_nodes)], dtype=np.int32)
    idx_map = {j: i for i, j in enumerate(idx)}
    edges_unordered = np.genfromtxt(path, dtype=np.int32)
    edges = np.array(list(map(idx_map.get, edges_unordered.flatten())),
                     dtype=np.int32).reshape(edges_unordered.shape)
    adj = sp.coo_matrix((np.ones(edges.shape[0]), (edges[:, 0], edges[:, 1])),
                        shape=(n, n), dtype=np.float32)
    # build symmetric adjacency matrix
    adj = adj + adj.T.multiply(adj.T > adj) - adj.multiply(adj.T > adj)
    adj = adj + sp.eye(adj.shape[0])
    adj = normalize(adj)
    # dense,csr matrix
    adj_dense = adj.todense()
    adj_csr = adj.tocsr()
    adj = sparse_mx_to_torch_sparse_tensor(adj)
    return adj,adj_csr, adj_dense

# 功能：读有序的adjlist图
# 输入：graph路径名，如 'bio30_ps.adjlist'(25023 nodes,968659 edges) 
# 输出：nx.graph, 其节点有序，含self loop
def load_ordered_adjlist_graph( fname ):
    G_nx = nx.read_adjlist(fname)
    G = nx.Graph() 
    print('initial G nodes {},edges {}'.format( G_nx.number_of_nodes(), G_nx.number_of_edges() ) )
    # node: int  edge: tuple(int, int)
    G.add_nodes_from( np.arange( G_nx.number_of_nodes() ) )        
    # symmetric edges
    for tup in G_nx.edges():
        elist = list( tup )
        G.add_edge( int(elist[0]),int(elist[1]) )
        G.add_edge( int(elist[1]),int(elist[0]) )
    for node in G_nx.nodes():
        G.add_edge( int(node), int(node) )
    # print( list(G.nodes())[:100]  )
    print('after G nodes {},edges {}'.format( G.number_of_nodes(), G.number_of_edges() ) )
    return G

# 功能：加载features
# 输入：加载features的名字，如'bio72'，'dpwk'
# 输出：Dataset实例，该实例含成员x
class load_data(Dataset):
    def __init__(self, name):
        print('reading {}.txt, please wait for about a thousand years....'.format(name))
        in_fname = './features/'+name+'.txt'
        self.x = np.loadtxt( in_fname, dtype=float)

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):
        return torch.from_numpy(np.array(self.x[idx])),\
            torch.from_numpy(np.array(idx))
    
# 功能：得到有序的嵌入特征
# 输入：无序的dpwk特征
# 输出：有序的dpwk特征
def preproc_embds_2_ordered():
    names = ['dpwk','line','lle','n2v']
    for name in names:
        in_fname = './mydata/embd_'+name+'.txt'
        out_fname = './mydata/ordered_'+name+'.txt'
        print('processing {}...'.format(in_fname))
        embd = np.loadtxt( in_fname,skiprows=1, dtype = float )
        x = [ [] for i in range(len(embd)) ]
        for i in range(len(embd)):
            idx = int(embd[i][0])
            feature = embd[i][1:]
            # if i==0:
            #     print('index:{},feature:{}'.format(idx,feature))
            x[idx] = feature
        np.savetxt( out_fname, x )

# 功能：adjlist文件转换为edgelist文件
# 输入：dpwk.adjlist
# 输出：dpwk.edgelist, 如 0 1 \n0 6
def myadj2edg():
    names = ['dpwk','line','lle','n2v']
    for name in names:
        in_fname = '../od2graphs/' + name + '.adjlist'
        out_fname = '../mygraph/' + name + '_edgelist.txt'
        edges = []
        with open( in_fname, 'r' ) as f:
            print( '{} reading...'.format(in_fname) )
            for i in range(3):
                line = f.readline()
            while True:
                line = f.readline()
                if not line:
                    break
                nodes = line.split()
                node, neighbours = nodes[0], nodes[1:]
                edges_line = [ [ int(node),int(neighbour) ] for neighbour in neighbours ]
                edges += edges_line
        print( '{} writing...'.format(out_fname) )
        np.savetxt( out_fname, edges, fmt='%d' )   
        
# 功能：合并相似度图和最近邻图
# 输入：bio30.adjlist  order1graph.adjlist
# 输出：bio30ps.txt    bio30ps.adjlist
def merge_graphs():
    fname1 = './mygraph/bio30.adjlist'
    fname2 = './mygraph/order1graph.adjlist'
    out_fname = './mygraph/bio30_ps.adjlist'
    out_fname2 = './mygraph/bio30_ps.txt'
    
    f = open(out_fname2,'w')
    G1 = nx.read_adjlist(fname1)         
    G2 = nx.read_adjlist(fname2)    
    print('G1:{} & G2:{} graphs merging...'.format(fname1,fname2))
    print('before:G1 edges:{},G2 edges:{}'.format(G1.number_of_edges(),G2.number_of_edges()))
    
    G_merge = nx.Graph()        # for sorted graph
    G_merge.add_nodes_from( G1.nodes() )
    for eg in G1.edges():           
        G_merge.add_edge(eg[0],eg[1])
    for eg in G2.edges():           
        G_merge.add_edge(eg[0],eg[1])
    print('after:G_merge edges:{}'.format(G_merge.number_of_edges()))
    nx.write_adjlist(G_merge,out_fname)  # write to adjlist file
    for eg in G_merge.edges():
        f.write('{} {}\n'.format(eg[0],eg[1]))
    f.close()       # open & close
    
    print('graphs merge over')
    print('nodes:G1:{},G2:{}'.format(G1.number_of_nodes(),G2.number_of_nodes()))
    
# 功能：数值不变，.csv文件转换为 .txt文件
# 输入：bio72.csv
# 输出：bio72.txt
def csv2txt():
    in_fname = '../bioBeforeApril/mydata/bio72.csv'
    out_fname = './features/bio72.txt'
    df = pd.read_csv(in_fname, header= 0, index_col= 0)
    x = np.array(df)
    np.savetxt(out_fname, x)

# 功能：测试utils内部函数
if __name__ == '':
    pass
