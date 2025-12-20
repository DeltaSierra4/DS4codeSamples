import random

class NimGraph:
    def __init__(self):
        self.graph = {}  

    def add_node(self, game_state):
        """Adds a node to the graph.

        Args:
            game_state: A tuple representing the number of objects in each pile.
        """
        if game_state not in self.graph:
            self.graph[game_state] = set()  # list of connected nodes

    def add_edge(self, start_state, end_state, weight=1):
        """Adds a directed edge with a weight.

        Args:
            start_state: The starting game state (tuple).
            end_state: The ending game state (tuple).
            weight: The weight associated with the edge (default 1). 
        """
        self.graph[start_state].add((end_state, weight))

    def recursive_graph_builder(self, init_state, weight=1):
        self.add_node(init_state)
        for i in range(len(init_state)):
            for j in range(1, init_state[i] + 1):
                modified_state = list(init_state)
                modified_state[i] -= j
                modified_state = tuple(modified_state)
                self.add_edge(init_state, modified_state, weight)

        for child_node in self.graph[init_state]:
            self.recursive_graph_builder(child_node[0], weight)


# Create an example graph for NIM
def create_nim_graph(init_state):
    graph = NimGraph()
    graph.recursive_graph_builder(init_state, 1)
    return graph


def deepcopy_nim_graph(graph):
    new_graph = NimGraph()
    for node, neighbors in graph.graph.items():
        new_graph.add_node(node)
        for neighbor, weight in neighbors:
            new_graph.add_edge(node, neighbor, weight)
    return new_graph

# Modify weights based on game history
def update_weights(graph, history):
    for start_state, end_state, is_winning_move in history:
        weight_adjustment = 2 if is_winning_move else -2

        # Find the existing weight (or default to 1 if not found)
        for neighbor, weight in graph.graph[start_state]:
            if neighbor == end_state:
                new_weight = weight + weight_adjustment
                graph.graph[start_state].remove((neighbor, weight))  # Remove old edge
                graph.graph[start_state].add((neighbor, new_weight))  # Add edge with new weight
                break

def random_player_move(game_state):
    """Makes a random move on a given NIM game state.

    Args:
        game_state: A tuple representing the current state of the game 
                    (number of objects in each pile).

    Returns:
        A tuple representing the new game state after the move.
        Alternatively, a tuple of all -1s if there are no valid moves.
    """

    # Find non-empty piles
    valid_piles = [idx for idx, pile_size in enumerate(game_state) if pile_size > 0]
    # Return a degenerate case if all piles are empty
    # since there are no moves to be made:
    if len(valid_piles) == 0:
        return tuple([-1] * len(game_state))

    # Choose a random non-empty pile 
    pile_to_modify = random.choice(valid_piles)

    # Choose a random number of objects to remove (between 1 and the pile size)
    num_objects_to_remove = random.randint(1, game_state[pile_to_modify])

    # Create the new game state
    new_game_state = list(game_state)
    new_game_state[pile_to_modify] -= num_objects_to_remove
    return tuple(new_game_state)

def play_random_nim(initial_state):
    """
    Imitates two players making random moves in Nim until the end state (0,0,0).

    Args:
        initial_state: The initial state of the game as a tuple.

    Returns:
        A list of game states from the initial state to the end state.
    """

    game_states = [initial_state]
    current_state = initial_state

    while current_state != (0, 0, 0):
        current_state = random_player_move(current_state)
        game_states.append(current_state)

    return game_states

def refine_game_history(game_history):
    refined_game_list = []
    """
        The logic behind this function:
        If there is an odd number of states in the game history, then player 1 won since they took the last object
        If there is an even number of states in the game history, then player 2 won since they took the last object
        The -1 from length adjusts for the initial state, which shouldn't count for number of moves
    """
    victor_flag = ((len(game_history) - 1) % 2 == 1)

    for i in range(1, len(game_history)):
        init_state = game_history[i - 1]
        next_state = game_history[i]
        refined_game_list.append((init_state, next_state, victor_flag))
        victor_flag = not victor_flag
    return refined_game_list

# Example usage:
default_state = (7, 5, 3)  # NIM with 3 piles, 7, 5, 3 objects initially
default_nim_graph = create_nim_graph(default_state)
nim_graph_copy = deepcopy_nim_graph(default_nim_graph)
training_loop_count = 1000

for i in range(training_loop_count):
    random_game = play_random_nim(default_state)

    # Define your game play history 
    # Format as the following: (starting state, ending state, was this the winning move?)
    game_history = refine_game_history(random_game)

    update_weights(nim_graph_copy, game_history)