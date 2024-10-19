import socket

class PeerProcess():
    def __init__(self, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size):
        self.numPrefNbors = num_pref_nbors
        self.unchoke_int = unchoke_int
        self.opt_unchoke_int = opt_unchoke_int
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size
        self.peers_info = dict()
        self.connections = dict()

    def add_peer(self, peer):
        self.peers_info[peer.peer_id] = peer
        self.connections[peer.peer_id] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections[peer.peer_id].connect((peer.host_name, peer.port_num))
        answer = self.connections[peer.peer_id].recv(1024)
        print(answer)
        handshake_header = make_handshake_header(peer.peer_id_int)
        #print(self.connections)
        sent = self.connections[peer.peer_id].send(handshake_header)
        print(sent)
        self.connections[peer.peer_id].close()

    def testing_print(self):
        print(self.numPrefNbors)
        print(self.unchoke_int)
        print(self.opt_unchoke_int)
        print(self.file_name)
        print(self.file_size)
        print(self.piece_size)

class PeerInfo():
    def __init__(self, peer_id, host_name, port_num, has_file):
        self.peer_id = peer_id
        self.peer_id_int = int(peer_id)
        self.host_name = host_name
        self.port_num = int(port_num)
        self.has_file = has_file == '1'

    def testing_print(self):
        print("PEER ID:", self.peer_id)
        print("HOST NAME", self.host_name)
        print("PORT NUM:", self.port_num)
        print("HAS FILE:", self.has_file)


def make_handshake_header(peer_id):
    initial_header = "P2PFILESHARINGPROJ".encode('utf-8')
    zero_bytes = bytearray(10)
    identifier = peer_id.to_bytes(4, byteorder = 'big')
    full_header = initial_header + zero_bytes + identifier
    return full_header