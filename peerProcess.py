class PeerProcess():
    def __init__(self, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size):
        self.numPrefNbors = num_pref_nbors
        self.unchoke_int = unchoke_int
        self.opt_unchoke_int = opt_unchoke_int
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size
        self.peers_info = list()

    def add_peer(self, peer):
        self.peers_info.append(peer)

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
        self.host_name = host_name
        self.port_num = port_num
        self.has_file = has_file == '1'

    def testing_print(self):
        print("PEER ID:", self.peer_id)
        print("HOST NAME", self.host_name)
        print("PORT NUM:", self.port_num)
        print("HAS FILE:", self.has_file)