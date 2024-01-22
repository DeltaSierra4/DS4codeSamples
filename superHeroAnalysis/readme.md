# Basic usage

You can run the script with the following command:

```
$ python3 csvloader.py <csv dataset> [options]
```

For instructions on what options are available, run the following command:

```
$ python3 csvloader.py -h
```

To run the script to provide answers to questions as requested, the following command will work:

```
$ python3 csvloader.py <csv dataset> -mo -ma -mc -st -si -cr -ra
```

If you want to run the script with different arguments, you can do so. For example, if you want to see the creator with the most Human type, you can use the following command:

```
$ python3 csvloader.py <csv dataset> -cwmst Human
```


# Usage for each question

For the answer to question 1 only, any of the following commands would work:

```
$ python3 csvloader.py <csv dataset> -mo -t -1 -rwmsa "" -cwmst "" -ra -1
$ python3 csvloader.py <csv dataset> -ma -t -1 -rwmsa "" -cwmst "" -ra -1
$ python3 csvloader.py <csv dataset> -mc -t -1 -rwmsa "" -cwmst "" -ra -1
```

For the answer to question 2 only, the following command would work:

```
$ python3 csvloader.py <csv dataset> -rwmsa "" -cwmst "" -ra -1
```

For the answer to question 3 only, the following command would work:

```
$ python3 csvloader.py <csv dataset> -t -1 -cwmst "" -ra -1
```

For the answer to question 4 only, any of the following command would work:

```
$ python3 csvloader.py <csv dataset> -t -1 -rwmsa "" -ra -1
```

For the answer to question 5 only, the following commands would work:

```
$ python3 csvloader.py <csv dataset> -st -si -cr -t -1 -rwmsa "" -cwmst "" -ra -1
```

For the answer to question 6 only, any of the following command would work:

```
$ python3 csvloader.py <csv dataset> -t -1 -rwmsa "" -cwmst ""
```


# Answers to each questions

1. Question 1: How would you define the most powerful superhero from the information available
in dataset?
The definition of the most powerful superhero can be defined in many different ways. The simplest measure is to simply refer to the overall_score. Another way is to compute the average score of the hero's stats, or simply to obtain a sum of all the stat scores. Another way is to count how many abilities a hero has. These methods are implemented as overall_power(), average_power(), and ability_counter()

2. Question 2: Find the top 5 superpowers in descending order.
We can tally_abilities() of superheroes to show the top x number of abilities. First, list_abilities() is called to extract the list of abilities in the dataframe, then the function iterates through each ability to tally the total by simply adding the values in the columns representing each ability (thanks to the fact that the columns represent boolean values of whether a superhero has an ability or not). Before the sum is obtained, however, the dataframe selection must be converted to a numeric value using pd.to_numeric() since the values are stored as strings initially.

3. Question 3: Which race has the most immortal superheroes?
We can tally_abilities_by_race() of superheroes to show which race has the most of a given ability. Input check is performed before iterating through all race types (gathered by the list_races() function) and simply adding up the values of a given ability boolean value. Also, as stated in list_races(), any row that is missing the race value is simply referred to as 'Unknown' (instead of using an empty string as recorded in the dataframe).

4. Question 4: Name the creator having most superheroes of type “Parademon”.
We can tally_race_by_creators() of superheroes to show which creator has the most of a given race. Simply search through the pandas dataframe by looking for matching data (in the case of question 4, look for rows where type_race matches the given race type for each creator), then count the number of rows.

5. Question 5: Which comic creator has the most superhero teams?
We can tally_teams_by_creators() of superheroes to show which creator has the most superhero teams. Sort the dataframe into subsets by creators, and then combine all team names into sets and tally the number of unique teams from each creator. (If there are no team names included in the dataset at all, then this function will print indicating such). Note that the csv file saved the list of team names as a string, but we want them in an object(list) format, so we use ast.literal_eval. The set of all team names sorted by creators is returned by this function to be used by crossover_check() to answer question 5b in the coding challenge. For this reason, only creators with any number of team names are considered. (i.e. any creator that doesn't have any team name will not be included)

Question 5a: Find names, real names and alias of superhero who is part of most teams.
We can find_hero_with_most_team() by going through the dataset by looking only at the columns name, real_name, full_name, and aliases as requested by question 5a. First, preprocess the dataset by removing any rows that don't have any team data at all (and exit the function if there are no rows that contain team data), then look for the row that contains the most number of teams and print the results.

Question 5b: Are there any crossovers between creators and teams?
We can crossover_check() between teams from each creator. Simple intersect() call over all creators and their sets of team names.

8. Question 6: Report on the 10 superheroes with most relatives, status of those relatives where possible, and the alignment of those superheroes.
We can run a relatives_alignment_report() to see the top x superheroes with relatives. Start off by pruning irrelevant data, then look for the 10 rows with the most members in the 'relatives' column by converting the dataframe into a json object and iterating through the top 10 results.
