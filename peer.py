from peerProcess import PeerProcess, PeerInfo
#Reading Common file
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
                num_pref_nbors = val
            case 'UnchokingInterval':
                unchoke_int = val
            case 'OptimisticUnchokingInterval':
                opt_unchoke_int = val
            case 'FileName':
                file_name = val
            case 'FileSize':
                file_size = val
            case 'PieceSize':
                piece_size = val
            case _:
                raise ValueError(f"Unrecognized key: {key}")
#Initializing PeerProcess
peer = PeerProcess(num_pref_nbors, unchoke_int, opt_unchoke_int, file_name, file_size, piece_size)
#Now reading all the peer info
with open('PeerInfo.cfg', 'r') as file:
    for line in file:
        words = line.split()
        if len(words) != 4:
            raise ValueError(f"Peer incorrectly identified for line {line}")
        peer.add_peer(PeerInfo(*words))