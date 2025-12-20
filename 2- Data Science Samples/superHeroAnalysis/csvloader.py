import json
import csv
import numpy as np
import pandas as pd
import plac

from ast import literal_eval
from collections import defaultdict


#
# Submission by Vincent Yang
# 
# For answers to questions 1 and 1a, refer to the functions overall_power(),
# average_power(), and ability_counter()
# For answer to question 2, refer to function tally_abilities()
# For answer to question 3, refer to function tally_abilities_by_race()
# For answer to question 4, refer to function tally_race_by_creators()
# For answer to question 5, refer to function tally_teams_by_creators()
# For answer to question 5a, refer to function find_hero_with_most_team()
# For answer to question 5b, refer to function crossover_check()
# For answer to question 8, refer to function relatives_alignment_report()


@plac.annotations(
    superhero_path=("csv file with superhero data", "positional", None, str),
    most_powerful_overall=(
        "List the most powerful superhero from each creator using overall \
score", "flag", "mo"),
    most_powerful_average=(
        "List the most powerful superhero from each creator using average \
score", "flag", "ma"),
    most_powerful_ability_count=(
        "List the most powerful superhero from each creator using count of \
abilities", "flag", "mc"),
    topxsp=(
        "Find the top x superpowers in dataset in descending order",
        "option", "t", int),
    topxsp_rev=(
        "Reverse the order of displaying results of top x superpowers",
        "flag", "tr"),
    race_with_most_superheroes_ability=(
        "Name the race having most superheroes of a certain ability. Use the \
column name for the argument", "option", "rwmsa", str),
    creator_with_most_superheroes_type=(
        "Name the creator having most superheroes of a certain type",
        "option", "cwmst", str),
    creator_with_most_superheroes_teams=(
        "Name the creator having most superhero teams",
        "flag", "st"),
    superhero_identity_most_teams=(
        "Find names, real names, and alias of superhero who is part of most \
teams.", "flag", "si"),
    crossover_between_creators_teams=(
        "Check for any crossovers between creators and teams.", "flag", "cr"),
    relatives_and_alignments=(
        "Show the top x superheroes in terms of number of relatives and \
report on their alignments.", "option", "ra", int)
)
def main(
    superhero_path,
    most_powerful_overall=False,
    most_powerful_average=False,
    most_powerful_ability_count=False,
    topxsp=5,
    topxsp_rev=False,
    race_with_most_superheroes_ability="has_immortality",
    creator_with_most_superheroes_type="Parademon",
    creator_with_most_superheroes_teams=False,
    superhero_identity_most_teams=False,
    crossover_between_creators_teams=False,
    relatives_and_alignments=10
):
    superhero_path = "superheroes_nlp_dataset.csv"
    spheroes = load_csv_to_pandas(superhero_path)
    spheroes_abilities = list_abilities(spheroes)
    spheroes_races = list_races(spheroes)
    spheroes_creators = list_creators(spheroes)
    teams_by_creators = {}

    print(spheroes_creators)
    print(spheroes_abilities)

    if most_powerful_overall:
        overall_power(spheroes, spheroes_creators)
    if most_powerful_average:
        average_power(spheroes, spheroes_creators)
    if most_powerful_ability_count:
        ability_counter(spheroes, spheroes_creators, spheroes_abilities)
    if topxsp > 0:
        tally_abilities(spheroes, spheroes_abilities, topxsp, topxsp_rev)
    if race_with_most_superheroes_ability:
        tally_abilities_by_race(
            spheroes, spheroes_races, 
            race_with_most_superheroes_ability, spheroes_abilities)
    if creator_with_most_superheroes_type:
        tally_race_by_creators(
            spheroes, spheroes_creators, creator_with_most_superheroes_type)
    if creator_with_most_superheroes_teams:
        teams_by_creators = tally_teams_by_creators(spheroes, spheroes_creators)
    if superhero_identity_most_teams:
        find_hero_with_most_team(spheroes)
    if crossover_between_creators_teams:
        crossover_check(teams_by_creators)
    if relatives_and_alignments > 0:
        relatives_alignment_report(spheroes, relatives_and_alignments)


# The definition of the most powerful superhero can be defined in many
# different ways. The simplest measure is to simply refer to the overall_score.
# Another way is to compute the average score of the hero's stats, or simply
# to obtain a sum of all the stat scores. Another way is to count how many
# abilities a hero has. These methods are listed out below in four methods
# overall_power(), average_power(), and ability_counter()


def overall_power(sppd, creators):
    results = {}
    for creator in creators:
        sppd_cr = sppd[(sppd['creator'] == creator)]
        highest_overall = max(sppd_cr.overall_score)
        sppd_highest = sppd_cr[sppd_cr['overall_score'] == highest_overall]
        if len(creator) == 0:
            creator = 'Unknown creator'
        results[creator] = [sppd_highest.name.unique(), highest_overall]

    for creator, result_list in results.items():
        if len(result_list[0]) == 1:
            print("{} is the strongest superhero created by {} at {} overall points".format(result_list[0][0], creator, result_list[1]))
        else:
            all_superheroes = ""
            for spname in result_list[0]:
                all_superheroes += spname + ", "
            all_superheroes = all_superheroes[:-2]
            print("The following heroes have tied at {} points for strongest superheroes created by {}: {}".format(result_list[1], creator, all_superheroes))
    print("")


def average_power(sppd, creators):
    results = {}
    for creator in creators:
        sppd_cr = sppd[(sppd['creator'] == creator)]
        sppd_cr_scores = sppd_cr[['intelligence_score', 'strength_score', 'speed_score', 'durability_score', 'power_score', 'combat_score']]
        highest_score = sppd_cr_scores.sum(axis=1).idxmax()
        highest_score_avg = max(sppd_cr_scores.sum(axis=1)) / 6
        herow = sppd_cr.loc[highest_score]
        results[creator] = [herow['name'], highest_score_avg]
    for creator, result_list in results.items():
        print("{} is the strongest superhero created by {} at {} average points".format(result_list[0], creator, result_list[1]))
    print("")


def ability_counter(sppd, creators, abilities):
    results = {}
    for creator in creators:
        sppd_cr = sppd[(sppd['creator'] == creator)]
        sppd_ab_list = sppd_cr['superpowers']
        biggest_list = max(sppd_ab_list, key=len)
        herow = sppd_cr[sppd_cr['superpowers'] == biggest_list].iloc[0]
        sp_all = herow.superpowers[1:-1]
        results[creator] = [herow['name'], len(sp_all.split(",")), sp_all]
    
    for creator, result_list in results.items():
        print("{} is the strongest superhero created by {} at {} unique superpowers: {}".format(result_list[0], creator, result_list[1], result_list[2]))
    print("")


# tally_abilities() of superheroes to show the top x number of abilities
# First, list_abilities() is called to extract the list of abilities
# in the dataframe, then the function iterates through each ability to
# tally the total by simply adding the values in the columns representing
# each ability (thanks to the fact that the columns represent boolean
# values of whether a superhero has an ability or not). Before the sum is
# obtained, however, the dataframe selection must be converted to a numeric
# value using pd.to_numeric() since the values are stored as strings initially


def tally_abilities(sppd, abilities, topcount, rev):
    results = {}
    for ability in abilities:
        ability_name = " ".join(ability.split("_")[1:])
        results[ability_name] = pd.to_numeric(sppd[ability]).sum()
    results_sorted = sorted(
        list(results.items()), key=lambda item : item[1], reverse=True)
    display_results = results_sorted[:topcount]
    if rev:
        display_results.reverse()
    print("The top {} abilities of superheroes are as the following".format(
        topcount))
    for ability_tally in display_results:
        print("{}: {} superheroes have this ability".format(
            ability_tally[0], int(ability_tally[1])))
    print("")  # End of question 2


# tally_abilities_by_race() of superheroes to show which race has the most
# of a given ability. Input check is performed before iterating through all
# race types (gathered by the list_races() function) and simply adding up
# the values of a given ability boolean value.
# Also, as stated in list_races(), any row that is missing the race value
# is simply referred to as 'Unknown' (instead of using an empty string
# as recorded in the dataframe).


def tally_abilities_by_race(sppd, races, ability, abilities):
    # Check for incorrect ability value
    if ability not in abilities:
        print("{} is not in the columns of the dataframe.".format(ability))
        print("Please make sure that you follow the formatting rules for \
abilities (i.e. you must use exact column names for ability checks).")
        return

    results = {}
    for race in races:
        sppd_race = sppd[sppd['type_race'] == race]
        if race == '':
            race = 'Heroes with Unknown race data'  # rows missing race name.
        results[race] = pd.to_numeric(sppd_race[ability]).sum()
    results_sorted = sorted(
        list(results.items()), key=lambda item : item[1], reverse=True)
    display_results = results_sorted[0]

    ability_display = " ".join(ability.split("_")[1:])
    print("The race with the most superheroes that have {} is the \
following: {}".format(ability_display, display_results[0]))
    print("")  # End of question 3


# tally_race_by_creators() of superheroes to show which creator has the most
# of a given race. Simply search through the pandas dataframe by looking for
# matching data (in the case of question 4, look for rows where type_race
# matches the given race type for each creator), then count the number of rows.


def tally_race_by_creators(sppd, creators, race):
    results = {}
    for creator in creators:
        sppd_cr = sppd[(sppd['creator'] == creator) & (sppd['type_race'] == race)]
        if creator == '':
            creator = 'Heroes with Unknown creator'  # rows missing creator.
        results[creator] = len(sppd_cr.index)
    results_sorted = sorted(
        list(results.items()), key=lambda item : item[1], reverse=True)
    display_results = results_sorted[0]
    print("The creator with the most superheroes that are of {} race is the \
following: {}".format(race, display_results[0]))
    print("")  # End of question 4


# tally_teams_by_creators() of superheroes to show which creator has the most
# superhero teams. Sort the dataframe into subsets by creators, and then
# combine all team names into sets and tally the number of unique teams from
# each creator. (If there are no team names included in the dataset at all,
# then this function will print indicating such).
# Note that the csv file saved the list of team names as a string, but we
# want them in an object(list) format, so we use ast.literal_eval. The set
# of all team names sorted by creators is returned by this function to be
# used by crossover_check() to answer question 5b in the coding challenge.
# For this reason, only creators with any number of team names are considered.
# (i.e. any creator that doesn't have any team name will not be included)


def tally_teams_by_creators(sppd, creators):
    results = {}
    results_ret = {}
    for creator in creators:
        sppd_cr = sppd[sppd['creator'] == creator]
        if creator == '':
            creator = 'Heroes with Unknown creator'  # rows missing creator.

        team_names = set(
            sppd_cr['teams'].apply(lambda x: literal_eval(x)).sum())
        if len(team_names) > 0:
            results[creator] = len(team_names)
            results_ret[creator] = team_names

    if len(results.items()) == 0:
        print("None of the creators in the dataset have superhero teams \
listed.")
    else:
        results_sorted = sorted(
            list(results.items()), key=lambda item : item[1], reverse=True)
        display_results = results_sorted[0]
        print("The creator with the most superhero teams is the \
following: {}".format(display_results[0]))
    print("")  # End of question 5
    return results_ret


# find_hero_with_most_team() by going through the dataset by looking only at
# the columns name, real_name, full_name, and aliases as requested by question
# 5a. First, preprocess the dataset by removing any rows that don't have any
# team data at all (and exit the function if there are no rows that contain
# team data), then look for the row that contains the most number of teams
# and print the results.


def find_hero_with_most_team(sppd):
    # First, filter out rows with no team names at all
    sppd_teams = sppd[(sppd['teams'] != '') & (sppd['teams'] != '[]')]
    if len(sppd_teams.index) == 0:
        print("The dataset contains no teams at all!")
        return

    sppd_teams_names = sppd_teams[['name', 'real_name', 'full_name', 'teams', 'aliases']]
    sppd_teams_list = sppd_teams['teams']
    biggest_list = max(sppd_teams_list, key=len)
    herow = sppd_teams_names[sppd_teams_names['teams'] == biggest_list].iloc[0]

    alias_all = herow.aliases[1:-1]
    team_all = herow.teams[1:-1]

    real_name = herow['real_name']
    if len(real_name) == 0:
        real_name = 'Unknown'
    full_name = herow['full_name']
    if len(full_name) == 0:
        full_name = 'Unknown'

    result_str = "{}, with real name {}, full name {}".format(herow['name'], real_name, full_name)
    if len(alias_all) > 0:
        result_str += ", along with the following aliases: {}".format(alias_all)
    result_str += ", is the member of most number of teams listed: {}". format(team_all)
    print(result_str)
    print("")  # End of question 5a


# crossover_check() between teams from each creator. Simple intersect() call
# over all creators and their sets of team names.


def crossover_check(teams_by_creators):
    team_crossovers = {}
    creators = list(teams_by_creators.keys())
    for c1 in range(len(creators)):
        for c2 in range(c1 + 1, len(creators)):
            if len(teams_by_creators[creators[c1]].intersection(teams_by_creators[creators[c2]])):
                team_crossovers["{} and {}".format(creators[c1], creators[c2])] = teams_by_creators[creators[c1]].intersection(teams_by_creators[creators[c2]])
    
    if len(team_crossovers.keys()) == 0:
        print("No crossovers of teams between creators in this dataset")
    else:
        for creators_pair, team_name_set in team_crossovers.items():
            team_name_all = ""
            for team_name in team_name_set:
                team_name_all += team_name + ", "
            team_name_all = team_name_all[:-2]
            print("{} share the following teams: {}".format(creators_pair, team_name_all))
    print("")  # End of question 5b


# relatives_alignment_report() to see the top x superheroes with relatives.
# Start off by pruning irrelevant data, then look for the 10 rows with the
# most members in the 'relatives' column.


def relatives_alignment_report(sppd, topx):
    # Prune out any superheroes without relatives
    sppd_rel = sppd[(sppd['relatives'] != '') & (sppd['relatives'] != '[]')]
    sppd_rel_al = sppd_rel[['name', 'alignment', 'relatives']]
    #print(sppd_rel_al)

    sppd_rel_al['len'] = sppd_rel_al['relatives'].str.len()
    sppd_rel_al = sppd_rel_al.sort_values(by='len', ascending=False).drop(columns='len')[:topx]

    results_json = json.loads(sppd_rel_al.to_json(orient='records'))
    print("The top 10 heroes with most relatives and their alignments are as follows:")
    for result in results_json:
        if len(result['alignment']) == 0:
            print("{} has no alignment and has the following relatives: {}".format(result['name'], result['relatives']))
        else:
            print("{} is aligned {} and has the following relatives: {}".format(result['name'], result['alignment'], result['relatives']))
    print("") # End of question 8


# Functions that are used to load/pre-process the dataframe for the functions
# to answer the coding challenge questions are listed below


def load_csv_to_pandas(path):
    return pd.read_csv(path, keep_default_na=False)


def list_abilities(sppd):
    # This function assumes that the abilities are listed in the dataset
    # in the form of 'has_xxxyyyzzz' where xxxyyyzzz corresponds to the
    # ability.
    abilities = []
    for cname in list(sppd.columns.values):
        cname_split = cname.split("_")
        if len(cname_split) > 1 and cname_split[0] == "has":
            abilities.append(cname)
    return abilities


def list_races(sppd):
    # 'Blank' races (i.e. rows with missing race values) will simply be
    # referred to as 'Unknown' in the result screen
    return list(sppd.type_race.unique())


def list_creators(sppd):
    # 'Blank' creators (i.e. rows with missing creator names) will simply be
    # referred to as 'Unknown' in the result screen
    return list(sppd.creator.unique())


if __name__ == '__main__':
    plac.call(main)