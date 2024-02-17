import random
import numpy as np
import json
from collections import defaultdict
from ordered_set import OrderedSet

class GameGraph:
    def __init__(self):
        self.graph = {}
        self.traversed = defaultdict(lambda: 0)
        #self.edges = defaultdict(lambda: 0)

    def add_node(self, game_state):
        """Adds a node to the graph.

        Args:
            game_state: A tuple representing the number of objects in each pile.
        """
        if type(game_state) == np.ndarray:
            game_state = str(game_state.tobytes())

        #if not (self.nodes[game_state]):
        if game_state not in self.graph:
            self.graph[game_state] = []  # List of connected nodes
            #self.nodes[game_state] += 1  # This node is now present
        #else:
        #    print("the one above didn't get in")

    def add_edge(self, start_state, end_state, weight=1):
        """Adds a directed edge with a weight.

        Args:
            start_state: The starting game state (tuple).
            end_state: The ending game state (tuple).
            weight: The weight associated with the edge (default 1). 
        """
        edge = str(end_state.tobytes()) + "::" + str(weight)
        target = str(start_state.tobytes())
        #relation = edge + "+" + target
        #if not (self.edges[relation]):
        if edge not in self.graph[target]:
            self.graph[target].append(edge)
            #self.edges[relation] += 1


    def iterative_graph_builder(self, init_state, init_player, shape, dtype, weight=1):
        queue = OrderedSet([(str(init_state.tobytes()), init_player)])
        loopno = 1
        swaps = 0
        old_player = 0

        while queue:
            if loopno%20000 == 0:
                print(len(queue))
                print(len(self.graph))
                #if loopno > 10000000000000:
                break
            #if loopno%200000 == 0:
            #    with open("blank_spot_model" + str(loopno) + ".json", "w+") as bmf:
            #        json.dump(self.graph, bmf, indent=4)
            current_state_str, current_player = queue.pop(0)
            if current_player != old_player:
                swaps += 1

            if swaps > 0 and swaps % 6 == 0:
                # Every 6 moves per player, save the model state
                with open("blank_spot_model_swap" + str(int(swaps / 6)) + ".json", "w+") as bmf:
                    json.dump(self.graph, bmf, indent=4)
                # refresh the current graph
                del self.graph
                self.graph = {}
                del self.traversed
                self.traversed = defaultdict(lambda: 0)
                swaps = 0

            current_state = str_to_array_converter(current_state_str, init_state.shape, init_state.dtype)
            self.add_node(current_state)
            next_player = 1 if current_player == 2 else 2
            valid_moves = valid_move_generator(current_state, current_player)
            possible_move_choice = list(valid_moves[1]) + valid_moves[2]

            for move in possible_move_choice:
                new_game_state = current_state.copy()
                new_game_state[move[1][0]][move[1][1]] = current_player
                if move[2] == 2:
                    new_game_state[move[0][0], move[0][1]] = 0
                # Check for any occupied neighbor squares after the move
                occupied_neighbors = check_occupied_neighbors(current_state, move[1], current_player)
                # Flip the pieces if there are opponent pieces in neighboring squares after the move
                if len(occupied_neighbors) > 0:
                    for row, col in occupied_neighbors:
                        new_game_state[row][col] = current_player
                self.add_edge(current_state, new_game_state, weight)
                reptar = str(new_game_state.tobytes()) + "::" + str(next_player)
                #if not np.array_equal(str(new_game_state.tobytes()), (x for x in self.graph.keys())):
                if not self.traversed[reptar]:
                    queue.add((str(new_game_state.tobytes()), next_player))
                    self.traversed[reptar] += 1
            loopno += 1
            old_player = current_player
            #swaps += 1


def str_to_array_converter(arraystr, shape, dtype):
    string_rep_enc = arraystr.encode()
    bytes_np_dec = string_rep_enc.decode('unicode-escape').encode('ISO-8859-1')[2:-1]
    backto_array = np.frombuffer(bytes_np_dec, dtype=dtype)
    return np.reshape(backto_array, shape)


# Create an example graph
def create_game_graph(init_state, init_player):
    graph = GameGraph()
    graph.iterative_graph_builder(init_state, init_player, init_state.shape, init_state.dtype, weight=1)
    return graph

def deepcopy_game_graph(graph):
    new_graph = GameGraph()
    for node, neighbors in graph.graph.items():
        new_graph.add_node(node)
        for neighbor, weight in neighbors:
            new_graph.add_edge(node, neighbor, weight)
    return new_graph

# Modify weights based on game history
def update_weights(graph, history):
    total_snags = 0
    for start_state, end_state, is_winning_move in history:
        end_state_bytes = str(end_state.tobytes())
        weight_adjustment = 2 if is_winning_move else -2

        # Find the existing weight (or default to 1 if not found)
        try:
            for neighbor, weight in graph.graph[str(start_state.tobytes())]:
                if neighbor == end_state_bytes:
                    new_weight = weight + weight_adjustment
                    graph.graph[str(start_state.tobytes())].remove((neighbor, weight))  # Remove old edge
                    graph.graph[str(start_state.tobytes())].add((neighbor, new_weight))  # Add edge with new weight
                    break
        except:
            #print("we hit a snag here:")
            #print(start_state)
            total_snags += 1
    print("Total number of snags: {}\n===================================================================".format(total_snags))


def get_neighbors(row, col):
    for dr, dc in [(0, 1), (1, 0), (1, 1), (0, -1), (-1, 0), (-1, -1), (-1, 1), (1, -1)]:
        yield row + dr, col + dc


def valid_move_generator(board, player):
    """
    Takes a board represented as a NumPy array and returns a list of all valid states.
    """

    valid_moves = {
        1: set(),
        2: []
    }
    for row in range(board.shape[0]):
        for col in range(board.shape[1]):
            if board[row, col] == player:
                # Check replication
                for nr, nc in get_neighbors(row, col):
                    if 0 <= nr < board.shape[0] and 0 <= nc < board.shape[1] and board[nr, nc] == 0:
                        move = (0, (nr, nc), 1)
                        valid_moves[1].add(move)

                # Check relocation (up to two squares away)
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        if abs(dr) + abs(dc) >= 2 and not (abs(dr) <= 1 and abs(dc) <= 1):
                            nr, nc = row + dr, col + dc
                            if 0 <= nr < board.shape[0] and 0 <= nc < board.shape[1] and board[nr, nc] == 0:
                                move = ((row, col), (nr, nc), 2)
                                valid_moves[2].append(move)
    return valid_moves


def check_occupied_neighbors(board, position, current_player):
    """
    Checks adjacent squares for opponent pieces and returns their coordinates.

    Args:
        board: The current board state as a NumPy array.
        position: A tuple (row, col) representing the coordinates to check around.
        current_player: The number of the player whose turn it is.

    Returns:
        A list of tuples (row, col) containing the coordinates of occupied
        opponent pieces adjacent to the given position.
    """

    row, col = position
    opponent_player = 1 if current_player == 2 else 2
    neighbors = []

    for dr, dc in [(0, 1), (1, 0), (1, 1), (0, -1), (-1, 0), (-1, -1), (-1, 1), (1, -1)]:
        nr, nc = row + dr, col + dc
        if 0 <= nr < board.shape[0] and 0 <= nc < board.shape[1] and board[nr, nc] == opponent_player:
            neighbors.append((nr, nc))

    return neighbors


def random_player_move(board, current_player):
    """Makes a random move on a given game state.

    Args:
        game_state: A numpy array showing the state of the board

    Returns:
        new_board: A numpy array showing the state of the board
    """

    valid_moves = valid_move_generator(board, current_player)
    possible_move_choice = list(valid_moves[1]) + valid_moves[2]
    # Return None if there are no moves to be made:
    if len(possible_move_choice) == 0:
        return None

    # Choose a random move
    random_move = random.choice(possible_move_choice)
    board[random_move[1][0]][random_move[1][1]] = current_player
    if random_move[2] == 2:
        board[random_move[0][0]][random_move[0][1]] = 0

    # Check for any occupied neighbor squares after the move
    occupied_neighbors = check_occupied_neighbors(board, random_move[1], current_player)

    # Flip the pieces if there are opponent pieces in neighboring squares after the move
    if len(occupied_neighbors) > 0:
        for row, col in occupied_neighbors:
            board[row][col] = current_player

    return board


def tally_player(board, player):
    return int(np.where(board == player, board, 0).sum() / player)


def play_random_spot(initial_state, starting_player):
    """
    Imitates two players making random moves in spot until all boards are filled.

    Args:
        initial_state: The initial state of the game as a numpy array.

    Returns:
        A dictionary containing the list of game states and the victor
    """

    game_states = [initial_state]
    current_state = initial_state.copy()
    current_player = starting_player
    winning_player = 0

    while True:
        new_state = random_player_move(current_state, current_player)
        if new_state is None:
            player1score = tally_player(current_state, 1)
            player2score = tally_player(current_state, 2)
            winning_player = 1 if player1score > player2score else 2
            break
        current_state = new_state
        game_states.append(current_state.copy())
        current_player = 1 if current_player == 2 else 2

    return {
        "game_states": refine_game_history(game_states, (starting_player == winning_player)),
        "winning_player": winning_player
    }

def refine_game_history(game_history, victor_flag):
    refined_game_list = []

    for i in range(1, len(game_history)):
        init_state = game_history[i - 1]
        next_state = game_history[i]
        refined_game_list.append((init_state, next_state, victor_flag))
        victor_flag = not victor_flag
    return refined_game_list


# Example usage:
init_board11 = np.array([
    [1, 0, 0, 0, 2],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [2, 0, 0, 0, 1]
], dtype=np.uint8)

starting_player = 1
game_graph = create_game_graph(init_board11, starting_player)

#with open("blank_spot_model.json", "w+") as bm:
#    json.dump(game_graph.graph, bm, indent=4)

print("Starting game (if you just wanted a blank model you can stop here)")

for i in range(1000):
    random_game = play_random_spot(init_board11, starting_player)

    # Refine your game play history 
    # Format as the following: (starting state, ending state, was this the winning move?)
    game_history = random_game["game_states"]

    print(len(random_game["game_states"]))
    if len(random_game["game_states"]) < 10:
        for d in random_game["game_states"]:
            break
            print(d[1])

    update_weights(game_graph, game_history)


#print(game_graph.graph)
#with open("trained_spot_model.json", "w+") as tm:
#    json.dump(game_graph.graph, tm, indent=4)