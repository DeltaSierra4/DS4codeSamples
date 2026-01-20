from openai import OpenAI
import random
import sys

"""
    A silly PoC where I make different models of GPT engage in a debate against one another over silly topics.
    Kudos to Neda Parnian for the initial suggestion.
"""

client = OpenAI(api_key="""YOUR API KEY""")

PERSONALITIES = [
    "a Chinese granny who is very skilled in Szechuan cuisine but lacks in English skill, so she only speaks in broken English.",  # shoutout to Hop Woo Chinese Cuisine!
    "an Italian Nonna who is very proud of her Italian cooking skills and has a sharp tongue for those who she deem as 'irreverent' towards Italian cuisine.",  # Italian Nonna vs Instagram star meme da bes!
    "a canny businessman who likes to take advantage of others through shrewd thinking and cunning wordsmanship, and he is extremely full of himself with megalomania.",  # American Psycho was an interesting movie
    "a big mime who cannot speak, but he gives sign languages and shows various facial expressions.",  # How would a mime participate in a debate?
    "an art-museum curator who has deep appreciation for art and is currently working to achieve tenure at a prestigious university.",  # shoutout to Prof. Gunther Wegner!
    "a cosplayer star who is famous on Instagram, she may seem very shallow on the outside but she has a heart of gold and is very kindhearted.",  # Sono bisque doll- er, I guess My Dressup Darling reference
    "a Twitch gamer who rages a lot.",  # Angry gamer moment! D:<
    "Captain Jack Sparrow.",  # SAY NO MORE
    "The Youtuber Markiplier."  # It's pronounced 'Ruhm' not 'Room'!
]
MODEL_CONFIGS = [
    {
        "model": "gpt-5",
        "reasoning": {"effort": "low"}
    },
    {
        "model": "gpt-5",
        "reasoning": {"effort": "high"}
    },
    {
        "model": "gpt-5.1",
        "reasoning": {"effort": "low"}
    },
    {
        "model": "gpt-5.1",
        "reasoning": {"effort": "high"}
    },
    {
        "model": "o3",
        "reasoning": {"effort": "low"}
    },
    {
        "model": "o3",
        "reasoning": {"effort": "high"}
    },
    {
        "model": "o3-mini",
        "reasoning": {"effort": "low"}
    },
    {
        "model": "o3-mini",
        "reasoning": {"effort": "high"}
    },
    {
        "model": "gpt-4",
        "reasoning": None,
        "temperature": 0.2
    },
    {
        "model": "gpt-3.5-turbo",
        "reasoning": None,
        "temperature": 0.2
    },
    {
        "model": "gpt-4o",
        "reasoning": None,
        "temperature": 0.2
    },
    {
        "model": "gpt-4",
        "reasoning": None,
        "temperature": 1.0
    },
    {
        "model": "gpt-3.5-turbo",
        "reasoning": None,
        "temperature": 1.0
    },
    {
        "model": "gpt-4o",
        "reasoning": None,
        "temperature": 1.0
    },
]
TOPICS = [
    "Does pineapple belong on pizza?",  # a classic debate topic that will never end.
    "What method is better to enjoy chicken wings: Pour the sauce over, or dip the wings into sauce?",  # a twist on a popular Korean food debate topic.
    "Which anime is better: Dragonball Z, Bleach, or Naruto?",  # the never ending debate that ripped through the mid-2000s
    "East Coast hip hop vs West Coast hip hop: Who did it better?",  # I might get some glares for this one...
    "Which SCP is the scariest in SCP containment breach and why?",  # Probably Radical Larry...
    "What is 8÷2(2+2)=?",  # the math problem that truly rocked the nation
    "Is Bigfoot real?",  # gotta love 'em cryptids ya know
    "Provide your own interpretation of the movie 'Inception'.",  # Believe it or not, my dormmates were torn apart by this one.
    "Which AI model of the following do you think is the best: Grok, Gemini, Claude, Mistral?"  # Excluding GPT because all models used here are GPT...
]
MAX_OUTPUT_TOKENS = 300

FULLY_RANDOMIZE = True  # Set to True for total chaos

class Bot_participant:
    def __init__(self, personality, model_config, topic):
        self.personality = personality
        self.model_config = model_config
        self.context = []
        self.name = " ".join(self.personality.split()[1:3])
        self.context=[
            {
                "role": "system",
                "content": f"You are {self.personality}. Today you are participating in a debate against other participants on the following topic: {topic}. When generating your response, DO NOT START WITH \"You say: \" or \"<some character name> says: \"."
            }
        ]
        if self.name == "big mime":
            """
                the mime personality tends to fail at generating responses... so let's give him a slight leverage.
            """
            self.context.append(
                {
                    "role": "developer",
                    "content": f"Although you are a mime and cannot speak, you should try to act out your responses by role-playing and using markdown language, e.g. *the mime frowns at your words and crosses his arms, clearly not pleased and grumpy at you.*"
                }
            )


    def bot_name(self):
        return self.name


    def bot_turn_wrapper(self, client):
        if len(self.context) == 1:
            self.context.append({
                "role": "developer",
                "content": f"You may make the first statement to start the debate. Go!"
            })
        return self.bot_turn(client)


    def bot_turn(self, client):
        if self.model_config["reasoning"]:
            response = client.responses.create(
                model=self.model_config["model"],
                reasoning=self.model_config["reasoning"],
                input=self.context,
                max_output_tokens=MAX_OUTPUT_TOKENS
            )
        else:
            response = client.responses.create(
                model=self.model_config["model"],
                temperature=self.model_config["temperature"],
                input=self.context,
                max_output_tokens=MAX_OUTPUT_TOKENS
            )
        self.context.append({
            "role": "assistant",
            "content": f"You say: {response.output_text}"
        })
        print(f"{self.name} says: {response.output_text}")
        return response.output_text


    def update_context(self, client, other_identity, other_response):
        self.context.append({
            "role": "user",
            "content": f"{other_identity} says: {other_response}"
        })


def stringify_config(config):
    model_intro = f"{config["model"]} with "
    if config["reasoning"]:
        model_intro += f"{config["reasoning"]["effort"]} reasoning capability."
    else:
        model_intro += f"response temperature set to {config["temperature"]}."
    return model_intro


def get_user_response(num_candidates, candidates, candidate_type):
    valid_input = False
    while not valid_input:
        print(f"You must give me {num_candidates} {candidate_type} to use for this debate. Give me a comma-separated input of {num_candidates} that you wish to use from the list shown below:")
        if candidate_type == "model configs":
            print("You may use the same model config for multiple candidates.")
            for i, candidate in enumerate(candidates):
                print(f"{i + 1}: {stringify_config(candidate)}")
        else:
            print("No two candidates may share the same personalities.")
            for i, candidate in enumerate(candidates):
                print(f"{i + 1}: {candidate}")
        user_input = input().split(",")
        try:
            user_input = [int(x.strip()) for x in user_input]
        except ValueError:
            print("Invalid input. Please try again.")
            continue
        if len(user_input) != num_candidates or any([x <= 0 for x in user_input]) or any([x > len(candidates) for x in user_input]):
            print(f"Invalid input. You must give me {num_candidates} {candidate_type} separated by commas and they must be within the range shown in the list. Please try again.")
            continue
        elif candidate_type == "personalities" and len(list(set(user_input))) != num_candidates:
            print(f"Invalid input. You must give me {num_candidates} different personalities - no two candidates may share the same personalities. Please try again.")
        valid_input = True
    return user_input


def choose_topic(topics):
    valid_input = False
    while not valid_input:
        print(f"Pick the topic of debate from the list shown below by typing in the number:")
        for i, top in enumerate(topics):
            print(f"{i + 1}: {top}")
        user_input = input()
        try:
            user_input = int(user_input.strip())
        except ValueError:
            print("Invalid input. Please try again.")
            continue
        if user_input > len(topics) or user_input <= 0:
            print(f"Invalid input. You must give me a single number that is within the range shown in the list. Please try again.")
            continue
        valid_input = True
    return user_input


def one_or_two(question):
    valid_input = False
    while not valid_input:
        print(question)
        user_input = input()
        try:
            user_input = int(user_input.strip())
        except ValueError:
            print("Invalid input. Please try again.")
            continue
        if user_input > 2 or user_input < 1:
            print("Invalid input. You must give me 1 or 2 as the answer. Please try again.")
            continue
        valid_input = True
    return (user_input == 1)


def main():
    while True:
        FULLY_RANDOMIZE = one_or_two("type 1 and hit enter for fully randomized experience, or 2 and hit enter for manual input.")
        TURN_LIMIT = random.randint(3, 10) if FULLY_RANDOMIZE else 5
        PARTICIPANTS = random.randint(2, 5) if FULLY_RANDOMIZE else 2
        participant_list = []
        if FULLY_RANDOMIZE:
            topic = random.choice(TOPICS)
            print(f"The topic of debate is: {topic}")
            personalities = random.sample(PERSONALITIES, PARTICIPANTS)
            model_configs = [MODEL_CONFIGS[random.randint(0, len(MODEL_CONFIGS) - 1)] for _ in range(PARTICIPANTS)]
            for i in range(PARTICIPANTS):
                participant_list.append(Bot_participant(personalities[i], model_configs[i], topic))
        else:
            topic = choose_topic(TOPICS)
            print(f"The topic of debate is: {TOPICS[topic - 1]}")
            personalities = get_user_response(PARTICIPANTS, PERSONALITIES, "personalities")
            model_configs = get_user_response(PARTICIPANTS, MODEL_CONFIGS, "model configs")
            for i in range(PARTICIPANTS):
                participant_list.append(Bot_participant(PERSONALITIES[personalities[i] - 1], MODEL_CONFIGS[model_configs[i] - 1], TOPICS[topic - 1]))

        participant_next_turn = participant_list.copy()
        for _ in range(TURN_LIMIT):
            participant_this_turn = random.choice(participant_next_turn)
            participant_next_turn = [participant for participant in participant_list if participant.bot_name() != participant_this_turn.bot_name()]
            participant_this_turn_statement = participant_this_turn.bot_turn_wrapper(client)
            for participant in participant_list:
                if participant != participant_this_turn:
                    participant.update_context(client, participant_this_turn.bot_name(), participant_this_turn_statement)

        start_new_session = one_or_two("type 1 and hit enter to spectate another debate, or 2 and hit enter to end the session.")
        if not start_new_session:
            break


if __name__ == "__main__":
    sys.exit(main())