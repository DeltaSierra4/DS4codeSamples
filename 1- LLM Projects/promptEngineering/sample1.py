import spacy
import backoff
import json
import logging
import matplotlib.pyplot as plt
import openai
import time
# Used by all packages

from pdf2image import convert_from_path
import easyocr
import numpy as np
import PIL
from PIL import ImageDraw
from IPython.display import display, Image
from spacy import displacy
# Used by pdf2image & easyocr

import pdfx
import pandas as pd
# Used by pdfx

import PyPDF2
# used by PyPDF2

import re


openai.api_key = 'YOUR_API_KEY'
openai.api_base = 'YOUR_BASE'
openai.api_type = 'YOUR_API_TYPE'
openai.api_version = 'YOUR_API_VER'


model_engine = "gpt-35-turbo-ds-1"


@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
def completions_with_backoff(**kwargs):
  return openai.ChatCompletion.create(**kwargs)


def create_response(model_engine, prompt, max_tokens, temp):
  # Generate a response
  msgs = [
      {'role':'user', 'content': prompt}
  ]
  completion = completions_with_backoff(
    engine=model_engine,
    messages=msgs,
    max_tokens=max_tokens,
    temperature=temp
  )

  response = completion.choices[0].message.content.strip().lower()

  if len(response) < 1:
    print(prompt)
    return 'none - GPT returned a blank response'

  return response


phones = phoneRegex.findall(text2)
emails = re.findall(extract_email_pattern, text2)

if len(names[j]) > 0:
namess = names[j].split()
namess[0] = (namess[0][0].upper() + namess[0][1:])
if len(namess) > 1:
  namess[1] = (namess[1][0].upper() + namess[1][1:])
if len(namess) > 2:
  namess[2] = (namess[2][0].upper() + namess[2][1:])
newname = " ".join(namess)
#print("name after capitalization: " + newname)
text2 = text2.replace(newname, "John Doe")
if len(phones) > 0:
text2 = text2.replace(phones[0][0], "555-555-5555")
for em in emails:
if "@" in em:
  text2 = text2.replace(em, "email@email.com")
#print(text2)

promptcompworks = f"""
A candidate for a job was asked to upload their resume, and they posted a \
file containing the following text delimited by triple backticks:
```{text2}```
Is this a resume or not? Follow these two rules when you answer:
1. You must only say yes or no as your answer.
2. If you cannot determine an answer, say no."""
ex = create_response(model_engine, promptcompworks, 1000, 0)
print(ex)


def makeEasierRead(text, wordCount):
  splits = text.split()
  print("this summary contains " + str(len(splits)) + " words.")
  splitlists = []
  row = []
  lastrow = []
  for word in splits:
    row.append(word)
    if len(row) >= wordCount:
      splitlists.append(row)
      row = []
    lastrow = row
  splitlists.append(lastrow)


  returnstr = ""
  for r in splitlists:
    addstr = " ".join(r)
    returnstr += (addstr + "\n")

  return returnstr

def resumetextcounter(text):
  splits = text.split()
  print("This resume has " + str(len(text)) + " characters and " + str(len(splits)) + " words.")

def generateResumeList(startno, endno, addlist=[]):
  for i in range(startno, endno):
    addlist.append("resume" + str(i) + ".pdf")
  return addlist
  
  
# Key to prompts:
# Sheet 3 - prompt1_old1 and prompt2_old1
# Sheet 4 - prompt1_old1 and prompt2
# Sheet 5 and 6 - prompts 1 and 2
#

def gpt_wrapper(text2, wordcount_j, wordcount_e, wordcount_s, nlp):
  llm = ChatOpenAI(
    temperature=0.0, openai_api_key=openai.api_key, engine='gpt-35-turbo-ds-1'
  )

  prompt1_old1 = ChatPromptTemplate.from_template("""
A candidate for a job has posted the following resume delimited by triple \
backticks:
```{resume_text}```
Summarize the candidate's professional experience in {wordcount_j} words or \
less. Make sure to follow these rules:
1. DO NOT INCLUDE ANY CONTACT INFO, SUCH AS ADDRESS, PHONE NUMBER, OR EMAIL.
2. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S EDUCATION OR DEGREE.
3. Start the summary with: \"The candidate is \" and their most recent job
experience.
4. The following line must never be included: \"powered by ZipRecruiter\".""")
  prompt1 = ChatPromptTemplate.from_template("""
A candidate for a job has posted the following resume delimited by triple \
backticks:
```{resume_text}```
Summarize the candidate's job experience in one sentence with {wordcount_j} \
words or less. Make sure to follow these rules:
1. DO NOT INCLUDE ANY CONTACT INFO, SUCH AS ADDRESS, PHONE NUMBER, OR EMAIL.
2. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S EDUCATION OR DEGREE.
3. Start the summary with: \"The candidate is \" and their most recent job
experience.
4. The following line must never be included: \"powered by ZipRecruiter\".""")

  prompt2_old1 = ChatPromptTemplate.from_template("""
A candidate for a job has posted the following resume delimited by triple \
backticks:
```{resume_text}```
Summarize the candidate's educational experience in one sentence with \
{wordcount_e} words or less. Make sure to follow these rules:
1. DO NOT INCLUDE ANY CONTACT INFO, SUCH AS ADDRESS, PHONE NUMBER, OR EMAIL.
2. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S JOB EXPERIENCE.
3. The following line must never be included: \"powered by ZipRecruiter\".""")
  prompt2 = ChatPromptTemplate.from_template("""
A candidate for a job has posted the following resume delimited by triple \
backticks:
```{resume_text}```
Summarize the candidate's educational experience in {wordcount_e} words or \
less. Make sure to follow these rules:
1. DO NOT INCLUDE ANY CONTACT INFO, SUCH AS ADDRESS, PHONE NUMBER, OR EMAIL.
2. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S JOB EXPERIENCE.
3. If the candidate has not graduated yet or graduation year is not \
specified, format the summary as the following: \"The candidate is pursuing \
a [degree name] at [institution name].\"
4. If the candidate has already graduated, format the summary as the \
following: \"The candidate graduated from [institution name] with a [degree \
name] in [graduation date].\"
5. The following line must never be included: \"powered by ZipRecruiter\".""")

  prompt3 = ChatPromptTemplate.from_template("""
A candidate for a job has posted the following resume delimited by triple \
backticks:
```{resume_text}```
If the resume has a separate section listing out the candidate's skillsets, \
summarize the candidate's skillsets in that section in {wordcount_s} words \
or less. Make sure to follow these rules:
1. DO NOT INCLUDE ANY CONTACT INFO, SUCH AS ADDRESS, PHONE NUMBER, OR EMAIL.
2. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S JOB EXPERIENCE.
3. DO NOT INCLUDE ANY INFORMATION ABOUT THE CANDIDATE'S EDUCATION OR DEGREE.
4. The following line must never be included: \"powered by ZipRecruiter\".""")

  prompt1_chain = LLMChain(llm=llm, prompt=prompt1, output_key="Work_exp")
  prompt2_chain = LLMChain(llm=llm, prompt=prompt2, output_key="Education")
  prompt3_chain = LLMChain(llm=llm, prompt=prompt3, output_key="Skillset")
  full_run = SequentialChain(
      chains=[prompt1_chain, prompt2_chain, prompt3_chain],
      input_variables=["resume_text", "wordcount_j", "wordcount_e", "wordcount_s"],
      output_variables=["Work_exp", "Education", "Skillset"]
  )
  response = full_run(
      {
          'resume_text': text2,
          'wordcount_j': wordcount_j,
          'wordcount_e': wordcount_e,
          'wordcount_s': wordcount_s
      }
  )
  workexp = makeEasierRead(response['Work_exp'], 915)
  education = makeEasierRead(response['Education'], 915)
  skillset = makeEasierRead(response['Skillset'], 915)
  wdef = "The candidate is an NLP Data Scientist at Veritone since November 2022."
  edef = "The candidate graduated from University of Pandologic with a B.S. in Computer Science in June 2022."
  sdef = "Python, MySQL, Linux, Git, spaCy."
  wdef = "The candidate is a Cook at WcDonalds from Aug 2019 - Jul 2022."
  edef = "The candidate is pursuing a B.S. in Computer Science at the University of Pandologic."
  sdef = "Forklift license, CCL, CPR certification."

  wsim = nlp(workexp).similarity(nlp(wdef))
  esim = nlp(education).similarity(nlp(edef))
  ssim = nlp(skillset).similarity(nlp(sdef))
  #print("skillset: " + skillset + " | noskill: " + no_skill + " | score: " + str(simsc))

  workexplen = len(workexp.split())
  educationlen = len(education.split())
  skillsetlen = len(skillset.split())
  print('Workexp (' + str(workexplen) + ' words, score: ' + str(wsim) + '): ' + workexp.strip())
  print('Education: (' + str(educationlen) + ' words, score: ' + str(esim) + '): ' + education.strip())
  print('Skillset: (' + str(skillsetlen) + ' words, score: ' + str(ssim) + '): ' + skillset.strip())
  rets = {
      'w': workexp,
      'e': education,
      's': skillset
  }
  return rets


def postprocess(ret, name, nlp, skillset_wordlimit):
  workexp = ret['w'].strip()
  education = ret['e'].strip()
  skillset = ret['s'].strip()

  # For workexp and education, transform summaries into a single sentence
  # if GPT returned multiple sentences.
  # The following lists should contain a single element if the summary is
  # in a single sentence. If not, then it contains multiple sentences.
  workexp_snt = [sntw for sntw in workexp.split(". ") if len(sntw.strip()) > 0]
  education_snt = [snte for snte in education.split(". ") if len(snte.strip()) > 0]
  if len(workexp_snt) > 1:
    workexp = sentence_concatenate(workexp, nlp)
  if len(education_snt) > 1:
    education = sentence_concatenate(education, nlp)
  #print(workexp_snt)
  #print(education_snt)

  # Start the summary with "{Candidate Name} is..."
  workexp = workexp.replace('The candidate', name, 1).strip()
  # Then join it to the education summary with a comma.
  if workexp[-1] == ".":
    workexp = workexp[:-1]
  workexp += ", "

  # Start the education summary with ", and he/she is..."
  if " ".join(education.split(" ")[0:2]) == "The candidate":
    education = education.replace('The candidate', 'and he/she', 1)
  else:
    noed = "No educational experience is listed on the candidate's resume."
    esimsc = nlp(noed).similarity(nlp(education))
    print("education: " + education + " | noed: " + noed + " | score: " + str(esimsc))
    if round(esimsc, 1) >= 0.8:
      # similarity is 90% or above. Consider this a case where candidate didn't list out educational experience.
      education = ""
    else:
      education = ("and their resume shows the following educational experience: " + education)

  if len(education) > 0:
    summary = (workexp + education).strip()
    if summary[-1] != ".":
      summary += "."
  else:
    summary = workexp

  skillset_prune = ["Skillsets:", 'Skills:']
  for prune_word in skillset_prune:
    skillset = skillset.replace(prune_word, '', 1).strip()

  if len(skillset.split()) > skillset_wordlimit:
    skillset = trim_skillset(skillset, skillset_wordlimit)

  no_skill = "No skillset section provided."
  simsc = nlp(no_skill).similarity(nlp(skillset))
  #print("skillset: " + skillset + " | noskill: " + no_skill + " | score: " + str(simsc))
  if round(simsc, 1) < 0.9:
    if summary[-1] == ".":
      summary += " The candidate's skills include: " + skillset
    else:
      summary += "and the candidate's skills include: " + skillset

  summary = summary.strip()
  if summary[-1] == ",":
    summary = summary[:-1] + "."

  print("++++++++++++++++")
  print(summary)
  return summary


def trim_skillset(text, skillset_wordlimit):
  # GPT sometimes throws a huge list of skills. We use a simple while loop
  # to trim down an item from the list until we meet the word limit criteria.
  skill_itemwise = text.split(", ")
  while len(", ".join(skill_itemwise).split()) > skillset_wordlimit:
    skill_itemwise = skill_itemwise[:-1]
  return ", ".join(skill_itemwise) + "."


def sentence_concatenate(snt, nlp):
  # Only called when we detect that a summary contains multiple sentences.
  # In that case, we use spacy to locate the period that marks the divider
  # between those sentences (here, we assume that GPT won't use other
  # punctuation marks such as ! or ?).
  ret = []
  doc = nlp(snt)
  #print([to.text for to in doc])
  for tk in range(len(doc)):
    if doc[tk].text == "." and tk != len(doc) - 1 and tk > 0:
      #print("len of doc: " + str(len(doc)) + " | tk: " + str(tk))
      # We have located the sentence divider. Remove it and throw in an
      # 'and' to concatenate the sentences together.
      # Possible TODO down the future: figure out a way if we can use
      # spacy to replace 'and' with 'but' if we want it to sound more
      # naturally.
      # e.g. "The candidate has no degree. He/she has a CDL license."
      # Current config: "The candidate has no degree, and he/she has a CDL
      # license." (fine, but sounds a bit awkward)
      # Suggested config: "The candidate has no degree, but he/she has a CDL
      # license." (sounds much more natural)
      ret[-1] += ','
      ret.append('and')
    elif len(ret) > 0 and (doc[tk].is_punct or \
     (len(doc[tk].text) >= 2 and doc[tk].text[0] == "'")):
      # Punctuations and apostrophes (e.g. He'll, She's, they're) must be
      # appended to the last word added.
      ret[-1] += doc[tk].text
    elif len(ret) > 1 and ret[-1] == 'and' and ret[-2][-1] == ",":
      # If the second sentence starts with a capital letter, lowercase() it
      # to make concatenation more natural. The only exception is if the 2nd
      # sentence begins with the pronoun 'I'.
      if doc[tk].text != "I":
        ret.append(doc[tk].text.lower())
      else:
        ret.append('I')
    else:
      ret.append(doc[tk].text)
  return(" ".join(ret))
 

  ret = gpt_wrapper(text2, 20, 20, 20)
  postprocess(ret, name, nlp, 20)