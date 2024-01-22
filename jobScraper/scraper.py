from bs4 import BeautifulSoup
import requests


def main():
	linx = ["https://www.jobapscloud.com//LACCD/auditor/ClassSpecs.asp?ShowAll=yes&R1=&R2=&R3=", "https://irecruitportal.ucr.edu/irecruit/!Controller?action=jobs_template&page=jobs_browser&public=true&profile_id="]

	for link in linx:
		domain = link.split('/')[2]
		job_posts = get_links(link, domain)

		for jlink in job_posts:
			response = requests.get(jlink).text
			if "python" in response.lower():
				print(jlink)


def get_links(url, domain):
	response = requests.get(url)
	data = response.text
	soup = BeautifulSoup(data, 'html.parser')

	links = []
	if "jobapscloud" in domain:
		for span in soup.find_all('span', {'class': 'cell first-cell'}):
			for link in span.find_all('a'):
				link_url = link.get('href')

				if link_url is not None:
					if link_url.startswith('https://' + domain):
						links.append(link_url)
	else:
		for span in soup.find_all('table', {'class': 'data2 tablesorter'}):
			for link in span.find_all('a'):
				link_url = link.get('href')

				if link_url is not None and link_url != "#":
					links.append('https://' + domain + '/irecruit/' + link_url)
	return links


def get_all_links(url):
	for link in get_links(url):
		get_all_links(link)


if __name__ == "__main__":
	main()