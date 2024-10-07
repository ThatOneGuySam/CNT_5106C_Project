class PeerProcess():
    def __init__(self, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size):
        self.numPrefNbors = num_pref_nbors
        self.unchoke_int = unchoke_int
        self.opt_unchoke_int = opt_unchoke_int
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size

    def testing_print(self):
        print(self.numPrefNbors)
        print(self.unchoke_int)
        print(self.opt_unchoke_int)
        print(self.file_name)
        print(self.file_size)
        print(self.piece_size)