import csv
import json
import openai
import os
import subprocess

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

from collections import defaultdict


openai.api_key = 'YOUR_API_KEY'
openai.api_base = 'YOUR_BASE'
openai.api_type = 'YOUR_API_TYPE'
openai.api_version = 'YOUR_API_VER'
model_engine = "gpt-35-turbo-ds-1"

CNA1 = '16086031'
CNA2 = '16086043'
reslim = 25

ResumesData = []
with open('sample_resume_urls3.csv', encoding='utf-8') as csvf:
  csvReader = csv.DictReader(csvf)
  for rows in csvReader:
    ResumesData.append(rows)

Questions = []
with open('sample_questions3.csv', encoding='utf-8') as csvf:
  csvReader = csv.DictReader(csvf)
  for rows in csvReader:
    Questions.append(rows)

questions_dic = defaultdict(lambda: [])
resumes_dic = defaultdict(lambda: [])

for q in Questions:
  if q['client_name'] == "Interim HealthCare Staffing":
    continue
  servecheck = " ".join(q['question'].split()[0:4])
  if servecheck.lower() == "please indicate law enforcement":
    q['question'] = "Do you have any previous law enforcement work experience? If so, " + q['question']
  questions_dic[q['job_sql_id']].append(q)
for r in ResumesData:
  if r['client_name'] == "Interim HealthCare Staffing":
    continue
  if len(resumes_dic[r['job_sql_id']]) < reslim:
    resumes_dic[r['job_sql_id']].append(r)

print(list(resumes_dic.keys()))

for k in resumes_dic.keys():
  try:
    os.mkdir('./' + k + '_resume')
  except FileExistsError as fee:
    pass


def runcmd(cmd, verbose = False, *args, **kwargs):
    process = subprocess.Popen(
        cmd,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        text = True,
        shell = True
    )
    std_out, std_err = process.communicate()
    if verbose:
        print(std_out.strip(), std_err)
    pass


for k in resumes_dic.keys():
  for i in range(len(resumes_dic[k])):
    filename = "./" + k + "_resume/resume" + str(i + 1) + ".pdf"
    pdfurl = resumes_dic[k][i]["resume_url"]
    if pdfurl is not None:
      wgetcom = "wget -O " + filename + " -c " + pdfurl
      runcmd(wgetcom)
    else:
      wgetcom = "wget -O " + filename + " -c " + resumes_dic[k][0]["z.resumeLink"]
      runcmd(wgetcom)

import re
from bs4 import BeautifulSoup

phoneRegex = re.compile(r'''(
    (\d{3}|\(\d{3}\))? # area code
    (\s|-|\.)? # separator
    (\d{3}) # first 3 digits
    (\s|-|\.) # separator
    (\d{4}) # last 4 digits
    (\s*(ext|x|ext.)\s*(\d{2,5}))? # extension
    )''', re.VERBOSE)
extract_email_pattern = r"\S+[ ]?@\S+[\.|_| ]\S+"


def preprocess_text(t, phoneRegex, extract_email_pattern, nlp):
  phones = phoneRegex.findall(t)
  emails = re.findall(extract_email_pattern, t)
  if len(phones) > 0:
    t = t.replace(phones[0][0], "")
  for em in emails:
    if "@" in em:
      t = t.replace(em, "")
  dates = []
  docd = nlp(t)
  if len(docd.ents) > 0:
    for de in docd.ents:
      if (de.label_ == 'DATE'):
        dates.append(de.text)

  for d in dates:
    t = t.replace(d, "")

  return t


def makeEasierRead(text, wordCount):
  splits = text.split()
  #print("this summary contains " + str(len(splits)) + " words.")
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

from IPython.lib.pretty import datetime
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.chains import SequentialChain


def gpt_yes_no(output_key, input_key, llm):
  prompt_raw = """A candidate for a job has the following resume delimited \
by triple backticks:
```{resume_text}```
A job recruiter for the same job asked the following question delimited \
by triple quote marks:
\"\"\"{""" + input_key + """}\"\"\"
Answer the question above based on the resume. Make sure to follow these \
rules:
1. You must say YES or NO as an answer. No other answers are accepted.
2. If an answer cannot be determined, you must say N/A."""
  prompt = ChatPromptTemplate.from_template(prompt_raw)
  return LLMChain(llm=llm, prompt=prompt, output_key=output_key)


def gpt_open_ended(output_key, input_key, wc, llm):
  prompt_raw = """A candidate for a job has the following resume delimited \
by triple backticks:
```{resume_text}```
A job recruiter for the same job asked the following question delimited \
by triple quote marks:
\"\"\"{""" + input_key + """}\"\"\"
Answer the question above based on the resume. Make sure to follow these \
rules:
1. You must answer the question in {""" + wc + """} words or less. DO NOT GO \
OVER THIS LIMIT UNDER ANY CIRCUMSTANCES.
2. If an answer cannot be determined, you must say N/A."""
  prompt = ChatPromptTemplate.from_template(prompt_raw)
  return LLMChain(llm=llm, prompt=prompt, output_key=output_key)


def gpt_wrapper(text, questions, t, engine):
  llm = ChatOpenAI(
    temperature=t, openai_api_key=openai.api_key, engine=engine
  )
  full_run_data = {
    'resume_text': text
  }
  chains = []
  input_variables = ["resume_text"]
  output_variables = []
  output_and_question = {}

  for i, q in enumerate(questions):
    question_text = "question" + str(i)
    output_key = "answer" + str(i)
    wc = "wc" + str(i)
    input_variables.append(question_text)
    output_variables.append(output_key)
    question_raw = q['question']
    if " ".join(question_raw.split()[:4]) == "Please indicate law enforcement":
      question_raw = "Do you have any previous law enforcement work experience? If yes, please indicate law enforcement agency, position, and date range."

    full_run_data[question_text] = question_raw
    output_and_question[output_key] = question_raw

    if q['qt'] == "Y/N":
      chains.append(gpt_yes_no(output_key, question_text, llm))
    else:
      chains.append(gpt_open_ended(output_key, question_text, wc, llm))
      input_variables.append(wc)
      if " ".join(q['question'].split()[:2]).lower() == "how many":
        # If the question is asking about time period, the answer will always
        # be available in 3 words or less.
        full_run_data[wc] = 3
      else:
        # Open ended question that can be responded in any number of words.
        # For brevity, limit it to 25 words or less.
        full_run_data[wc] = 25

  full_run = SequentialChain(
      chains=chains,
      input_variables=input_variables,
      output_variables=output_variables
  )
  response = full_run(full_run_data)

  for o in output_variables:
    a = output_and_question[o] + "------" + response[o]
    print(makeEasierRead(a, 99915))


na = "15947815"
names = [
  # List of candidate names
]

alrr4 = [
  # List of pdf files
]

for i, resume_patho in enumerate(alrr4):
  resume_patho = "./" + na + "_resume/" + resume_patho
  name = names[i]
  print("GPT results for " + resume_patho + ":\n")

  try:
    reader = easyocr.Reader(['en'])
    images = convert_from_path(resume_patho)
    bounds = []
    for img in images:
      bounds += reader.readtext(np.array(img), min_size=0, slope_ths=0.2,
                                ycenter_ths=0.7, height_ths=0.6, width_ths=0.8,
                                decoder='beamsearch', beamWidth=10)

    text2 = ''
    for jk in range(len(bounds)):
      text2 = text2 + bounds[jk][1] +'\n'
    #print(text2)
  except:
    try:
      print("This resume can't be parsed on OCR: " + resume_patho)
      pdf = pdfx.PDFx(resume_patho)
      text2 = pdf.get_text()
    except:
      print("This resume can't be parsed. Skipping.")
      continue

  phones = phoneRegex.findall(text2)
  emails = re.findall(extract_email_pattern, text2)

  j = i

  if len(names[j]) > 0:
    namess = names[j].split()
    namess[0] = (namess[0][0].upper() + namess[0][1:])
    if len(namess) > 1:
      namess[1] = (namess[1][0].upper() + namess[1][1:])
    if len(namess) > 2:
      namess[2] = (namess[2][0].upper() + namess[2][1:])
    newname = " ".join(namess)
    text2 = text2.replace(newname, "John Doe")
  if len(phones) > 0:
    text2 = text2.replace(phones[0][0], "555-555-5555")
  for em in emails:
    if "@" in em:
      text2 = text2.replace(em, "email@email.com")

  gpt_wrapper(text2, questions_dic[na], 0.0, model_engine)
  print("===============================================================")