import sys
import os
import math
import socket

class PeerProcess():
    def __init__(self, id, host_name, port, has_file, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size, next_peers):
        self.id = id
        self.host_name = host_name
        self.port = port
        self.has_file = has_file
        
        self.numPrefNbors = num_pref_nbors
        self.unchoke_int = unchoke_int
        self.opt_unchoke_int = opt_unchoke_int
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size
        
        self.num_pieces = int(math.ceil(file_size/piece_size))
        self.bitfield = self.initialize_bitfield(has_file)
        self.next_peers = next_peers
        
        self.peers_info = dict()
        self.connections = dict()
        self.listening_socket = self.initialize_socket(host_name, port)
        self.subdir = f"{os.getcwd()}/peer_{str(self.id)}"
        if not os.path.exists(self.subdir):
            os.mkdir(self.subdir)
        
    def initialize_bitfield(self, has_file):
        length = math.ceil(self.num_pieces / 8) * 8
        remainder = (8 - (self.num_pieces % 8)) % 8
        if has_file:
            #Set all bits to one except remainder
            bitfield = '1'*(length-remainder) + '0'*(remainder)
        else:
            bitfield = '0'*(length)
        bitfield_int = int(bitfield,2)
        return bitfield_int.to_bytes(length // 8, byteorder='big')

    def initialize_socket(self, host_name, port):
        curr_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        curr_socket.bind((host_name, port))
        curr_socket.listen(5)
        return curr_socket
    
    def make_handshake_header(self, peer_id):
        initial_header = "P2PFILESHARINGPROJ".encode('utf-8')
        zero_bytes = bytearray(10)
        identifier = peer_id.to_bytes(4, byteorder = 'big')
        full_header = initial_header + zero_bytes + identifier
        return full_header

    def add_peer(self, peer):
        self.peers_info[peer.peer_id] = peer
        self.connections[peer.peer_id] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections[peer.peer_id].connect((peer.host_name, peer.port_num))
        self.connections[peer.peer_id].send(self.make_handshake_header(self.id))
        answer = self.connections[peer.peer_id].recv(1024)
        print(answer)
        if answer != self.make_handshake_header(peer.peer_id):
            raise RuntimeError("Unexpected header, something with the connection has failed")

    def wait_for_connection(self):
        conn, addr = self.listening_socket.accept()
        header = conn.recv(1024)
        print(header)
        byte_conn_id = header[-4:]
        conn_id = int.from_bytes(byte_conn_id, "big")
        curr_peer = None
        for next_peer in self.next_peers:
            if next_peer.peer_id == conn_id:
                curr_peer = next_peer
                break
        if not curr_peer:
            raise RuntimeError("Header has an incorrect peer id")
        self.peers_info[curr_peer.peer_id] = curr_peer
        self.connections[curr_peer.peer_id] = conn
        self.next_peers.remove(curr_peer)
        self.connections[curr_peer.peer_id].send(self.make_handshake_header(self.id))

class PeerInfo():
    def __init__(self, peer_id, host_name, port_num, has_file):
        self.peer_id = int(peer_id)
        self.host_name = host_name
        self.port_num = int(port_num)
        self.has_file = has_file == '1'

    def testing_print(self):
        print("PEER ID:", self.peer_id)
        print("HOST NAME", self.host_name)
        print("PORT NUM:", self.port_num)
        print("HAS FILE:", self.has_file)




def main():
    if len(sys.argv) < 2:
        raise SyntaxError("Need to provide a peer ID argument")
    id = int(sys.argv[1])
    host_name = None
    port = None
    prev_peers = list()
    next_peers = list()
    #Get previous peers and this peer's port number
    with open('PeerInfo.cfg', 'r') as file:
        for line in file:
            words = line.split()
            if len(words) != 4:
                raise ValueError(f"Peer incorrectly identified for line {line}")
            if int(words[0]) == id and port:
                raise ValueError(f"Peer incorrectly appears multiple times")
            if int(words[0]) == id:
                host_name = words[1]
                port = int(words[2])
                has_file = words[3] == '1'
            elif not port:
                prev_peers.append(PeerInfo(*words))
            else:
                next_peers.append(PeerInfo(*words))
    #If peer never found, throw error
    if not port:
        raise ValueError("Given Peer ID was not found in PeerInfo.cfg file")
    #Now Reading Common file and Setting values
    with open('Common.cfg', 'r') as file:
        #I'm going to get a little overcomplicated here, but I want to be prepared
        #for the case where the config file is given if a different order.
        for line in file:
            words = line.split()
            if len(words) == 0:
                continue
            elif len(words) == 1:
                raise ValueError(f"Missing variable for line {line}")
            key = words[0]
            val = words[1]
            match key:
                case 'NumberOfPreferredNeighbors':
                    num_pref_nbors = int(val)
                case 'UnchokingInterval':
                    unchoke_int = int(val)
                case 'OptimisticUnchokingInterval':
                    opt_unchoke_int = int(val)
                case 'FileName':
                    file_name = val
                case 'FileSize':
                    file_size = int(val)
                case 'PieceSize':
                    piece_size = int(val)
                case _:
                    raise ValueError(f"Unrecognized key: {key}")
    #Initializing PeerProcess
    peer = PeerProcess(id, host_name, port, has_file, num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size, next_peers)
    #Now make the previous connections
    for prev_peer in prev_peers:
        peer.add_peer(prev_peer)
    #Now set up acceptance for other connections
    while len(peer.next_peers) > 0:
        peer.wait_for_connection()

    print("We made it")
    for conn in peer.connections.values():
        conn.close()
    peer.listening_socket.close()


if __name__ == "__main__":
    main()