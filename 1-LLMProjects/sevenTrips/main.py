from openai import OpenAI
client = OpenAI(api_key="""YOUR API KEY""")


def basic_revision(client, position, userinput):
    system = f"""
Rewrite my resume for the role of {position}. My resume is delimited by three backticks, and the Job posting is delimited by three single quotation marks.
Follow the following rules:
1. DO NOT MAKE UP EXPERIENCE THAT IS NOT INCLUDED IN THE ORIGINAL USER RESUME.
2. Do not use markdown formatting anywhere.
3. Each job experience must have exactly two bullet points, each bullet point must be relevant to the job position.
4. Use confident, achievement-focused language.
5. Quantify results wherever possible (numbers, %, impact)
6. Remove weak or generic phrases.
7. Match the tone of modern tech/startup resumes.
    """

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        instructions=system,
        input=userinput
    )

    print(response.output_text + "\n\n\n" + "*" * 80)
    return response.output_text


def standard_revision(client, position, userinput):
    system = f"""
You are an expert recruiter and resume writer. You are hiring candidates for the role of {position}, and today you have been approached by an applicant
who is asking for your expertise in resumes to match what you actually scan for in 10 seconds.

My resume is delimited by three backticks, and the Job posting is delimited by three single quotation marks.
Follow the following rules:

1. DO NOT MAKE UP EXPERIENCE THAT IS NOT INCLUDED IN THE ORIGINAL USER RESUME.
2. Rewrite my experience using numbers, impact, and outcomes. Remove responsibilities. Keep only results.
3. Each job experience must have exactly two bullet points, each bullet point must be relevant to the job position.
4. Use confident, achievement-focused language.
5. Quantify results wherever possible (numbers, %, impact)
6. Remove weak or generic phrases.
7. Match the tone of modern tech/startup resumes.
8. Optimize my resume for ATS keywords for this job description without sounding robotic.”
9. Do not use markdown formatting anywhere.
10. Cut my resume down to one page while increasing clarity and relevance."""

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        instructions=system,
        input=userinput
    )

    print(response.output_text + "\n\n\n" + "*" * 80)
    return response.output_text


def comprehensive_revision(client, position, userinput):
    system = f"""
You are an expert recruiter and resume writer. Help me improve my resume for {position} so it clearly reflects my real experience, sounds like me, and positions me strongly for the roles I’m targeting, increasing my chances of landing interviews.

NON-NEGOTIABLE RULES:
1. Do not invent, exaggerate, or assume anything (experience, metrics, employers, titles, tools, certifications, dates).
2. If information is missing or unclear, ask me before writing.
3. Keep my voice human and confident. No corporate fluff.
4. Do not copy wording from job postings. Translate my real experience into relevant language.
5. Optimize for humans and ATS: clear structure, clean formatting, keyword alignment without stuffing.

{userinput}

STEP 1: After reviewing everything, summarize:
* The top 8–12 skills/keywords across the postings
* The 3–5 outcomes the hiring manager likely cares most about
* The biggest gaps or weaknesses in my resume for these roles

STEP 2: Deliver the following:
A) A tailored, ATS-friendly resume (no tables, no columns) including:
  - A strong headline and 2-line summary
  - Core Skills under each relevant job (10–14 max)
  - Experience bullets written as: Action + Scope + Outcome
  - Tight bullets (1–2 lines), most relevant first
B) A change log explaining what you changed and why
C) A truth check list of anything that still needs my confirmation

FORMATTING
* Use standard headings only: Summary, Core Skills, Experience, Education, Certifications
* Present tense for current roles; past tense for previous roles
* Use strong verbs and specific outcomes
* No buzzwords, clichés, graphics, icons, or heavy design
"""

  response = client.responses.create(
      model="gpt-5",
      reasoning={"effort": "low"},
      instructions=system,
      input=userinput
  )

  print(response.output_text + "\n\n\n" + "*" * 80)
  return response.output_text


def combine_resumes(client, position, resumes):
    system = f"""
You are an expert resume writer. Today your job is to look over three resumes written for the same position of {position} and combine them together to a single resume for the position.
Follow the following rules:

1. DO NOT MAKE UP EXPERIENCE THAT IS NOT INCLUDED IN THE ORIGINAL USER RESUME.
2. Each job experience must have exactly two bullet points, each bullet point must be relevant to the job position.
3. Use confident, achievement-focused language and remove weak or generic phrases. Match the tone of modern tech/startup resumes.
4. Optimize the resume for ATS keywords for this job description without sounding robotic.
5. Do not use markdown formatting anywhere.
6. Cut the resume down to one page while increasing clarity and relevance."""

    input_array = [
        {
            "role": "system",
            "content": system
        }
    ]
    for resume in resumes:
        input_array.append({
            "role": "user",
            "content": resume
        })

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        input=input_array
    )

    print(response.output_text)


def select_version():
    valid_input = False
    while not valid_input:
        print("""Type 1 and hit enter to run a very basic resume revision.
Type 2 and hit enter to run standard resume revision.
Type 3 and hit enter to run comprehensive resume revision.
Type 4 and hit enter to run all resume revisions and obtain a combined resume.\n""")
        user_input = input()
        try:
            user_input = int(user_input.strip())
        except ValueError:
            print("Invalid input. Please try again.")
            continue
        if user_input > 4 or user_input < 1:
            print("Invalid input. You must give me a number between 1 and 4 inclusive as the answer. Please try again.")
            continue
        valid_input = True
    return user_input


def main():
    """Main function."""
    import argparse
    import scanner as sp
    
    parser = argparse.ArgumentParser(
        description="AI-powered resume revision script"
    )
    parser.add_argument("resume_path", help="Path to the resume file. Must be .pdf, .doc, .docx, or .txt") 
    parser.add_argument("jd_path", help="Path to the job description file. Must be .pdf, .doc, .docx, or .txt")
    args = parser.parse_args()
    
    resume_scanned = sp.scan(resume_path)
    jd_scanned = sp.scan(jd_path)

    print("What position are you applying to?")
    position = input()

    userinput = f"""
User resume:```{resume_scanned}```
--------------------------------------------------------------------------------------------------------
Job posting:'''{jd_scanned}'''"""

    versions = {
        1: basic_revision,
        2: standard_revision,
        3: comprehensive_revision,
        4: combine_resumes
    }
    ver = select_version()

    if ver == 4:
        combine_resumes(client, position, [basic_revision(client, position, userinput), standard_revision(client, position, userinput), comprehensive_revision(client, position, userinput)])
    else:
        versions[ver](client, position, userinput_resume)


if __name__ == "__main__":
    sys.exit(main())