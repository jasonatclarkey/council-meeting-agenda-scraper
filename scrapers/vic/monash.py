import sys
from pathlib import Path

parent_dir = str(Path(__file__).resolve().parent.parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from base_scraper import BaseScraper, register_scraper
from logging.config import dictConfig
from _dataclasses import ScraperReturn
from bs4 import BeautifulSoup
import re
import json
import requests
from datetime import datetime


@register_scraper
class MonashScraper(BaseScraper):
    def __init__(self):
        council = "monash"
        state = "VIC"
        base_url = "https://www.monash.vic.gov.au"
        self.date_pattern = re.compile(
            r"\b(\d{1,2})\s(January|February|March|April|May|June|July|August|September|October|November|December)\s(\d{4})\b"
        )
        self.time_pattern = re.compile(r"\b\d{1,2}:\d{2} [apmAPM]+\b")
        super().__init__(council, state, base_url)

    def scraper(self) -> ScraperReturn | None:
        self.logger.info(f"Starting {self.council_name} scraper")
        meeting_schedules = "/About-Us/Council/Council-Meetings/Council-Meetings-Schedule"

        name = []
        date = None
        time = None
        download_url = []
        # link_to_agenda = None

        # Heads up!
        # This is not simple.
        # There is a CDN in front of this that may are-you-a-human-check you.
        # Then, the page requires an call off to another endpoint, probably some sort
        # of DMS/LMS/CRN.
        # EVEN THEN you don't get one PDF, you get a list.. ex:
        # 7.1.1. Town Planning Schedule Report
        # 7.1.2. 319-321 Springvale Road, Glen Waverley Development
        # 7.1.3. TPA/40955D - 170-174 Highbury Rd Mount Waverley
        # 7.1.4. 21 Banksia Street Clayton Construction - Extension of Time
        # 7.2.1. Gender Equality Act 2020 Reporting Progress
        # 7.2.2. 2023/24 Monash Quick Response Grants Program Recipients
        # 7.2.3. Draft Monash Cricket Participation Plan
        # 7.3.1. 2024092 - Cisco Internet Protocol Telephony
        # 8.1. NOM - Councillor Discretionary Fund
        # 10.1. Proposed Sale of Central Car Park, Glen Waverley
        # Each with their own PDF.
        # This will require refactoring to support.
        # Looks like this: https://github.com/yimbymelbourne/council-meeting-agenda-scraper/issues/22
        # So we'll hit their public page.
        # Get a cookie
        # Post to another endpoint
        # Parse the JSON
        # Build a list of PDFs
        meeting_agendas = "/About-Us/Council/Council-Meetings/Agendas-Minutes"

        # Lets just log when the next Agenda will be published.
        # Just for the curious of mind.
        output = self.fetch_with_selenium(self.base_url + meeting_schedules)
        schedule_soup = BeautifulSoup(output, "html.parser")
        next_meeting_heading = schedule_soup.find("h1", class_="oc-page-title")
        if next_meeting_heading:
            next_meeting_content = next_meeting_heading.find_next("p")
            if next_meeting_content:
                next_meeting_date = next_meeting_content.find("strong").text
                self.logger.info(f"Next meeting: {next_meeting_date}")
                next_agenda_available_content = next_meeting_content.find_next("p")
                if next_agenda_available_content:
                    next_agenda_available = next_agenda_available_content.find("strong").text
                    self.logger.info(f"Next meeting agenda available after: {next_agenda_available}")
                else:
                    self.logger.error(f"Failed to find information about next meeting schedule, did the webpage change? {self.base_url}{meeting_schedules}\n{schedule_soup}")
                    return None
            else:
                self.logger.error(f"Failed to find information about next meeting schedule, did the webpage change? {self.base_url}{meeting_schedules}\n{schedule_soup}")
                return None
        else:
            self.logger.error(f"Failed to find information about next meeting schedule, Maybe we hit a are-you-a-human-check? {self.base_url}{meeting_schedules}\n{schedule_soup}")
            # This is what the are-you-a-human-check looks like.
            # <body style="margin:0px;height:100%">
            # 	<iframe frameborder="0" height="100%" id="main-iframe" marginheight="0px" marginwidth="0px" src="/_Incapsula_Resource?SWUDNSAI=31&amp;xinfo=10-28084829-0%200CNN%20RT%281707353416487%2035%29%20q%280%20-1%20-1%20-1%29%20r%280%20-1%29%20B12%284%2c315%2c0%29&amp;incident_id=413000880069676471-136291149259019786&amp;edet=12&amp;cinfo=04000000&amp;rpinfo=0&amp;cts=gUFVjzcd2cmBUBT%2bbxgq%2fBHVZVrrvmVvQlWl2iZDtUOwYrVVC9VQXFI3r4Nk9wJ8&amp;mth=GET" width="100%">
            # 		Request unsuccessful. Incapsula incident ID: 413000880069676471-136291149259019786
            # 	</iframe>
            # </body>
            robot_check = schedule_soup.find("iframe").get_text()
            if "Request unsuccessful. Incapsula incident ID" in robot_check:
                self.logger.info("We've hit a are-you-a-human-check, try to continue. Good luck adventurer!")
            else:
                self.logger.info(f"Something else broke, here's the HTML, good luck: {schedule_soup.prettify()}")
                return None
        
        
        # Lets grab some PDFs, I mean, ZIPs, with a cookie
        output, cookies = self.fetch_with_selenium_return_cookies(self.base_url + meeting_agendas)

        # From the looks of it, we need a `incap_ses_413_2508499` cookie for later.
        # Obviously the number are going to be random. Lets try our luck.
        cookie_on_a_diet = {}
        for c in cookies: # nom nom
            if c['name'].startswith("incap_ses_"):
                cookie_on_a_diet['name'] = c['name']
                cookie_on_a_diet['value'] = c['value']
                break

        initial_soup = BeautifulSoup(output, "html.parser")

        accordian_content = initial_soup.find("div", class_="minutes-list-container")
        if accordian_content:
            article_content = accordian_content.find("article")
            if article_content:
                cvid=accordian_content.find("a")["data-cvid"]
                dt = datetime(2024, 2, 7, 5, 28, 43, 655)
                cache_buster = dt.strftime('%Y-%m-%dT%H%%3A%M%%3A%S.%fZ')
                # Example: e9240107-29d8-4560-a5ac-7bf6cecc9909
                # Example: https://www.monash.vic.gov.au/OCServiceHandler.axd?url=ocsvc/Public/meetings/documentrenderer&keywords=&cvid=d90947c9-1626-4f04-b087-f3d7810fddd7&cachebuster=2024-02-07T05%3A28%3A43.655Z
                # Example: https://www.monash.vic.gov.au/About-Us/Council/Council-Meetings/Agendas-Minutes
                url = self.base_url+"/OCServiceHandler.axd?url=ocsvc/Public/meetings/documentrenderer&keywords=&cvid="+cvid+"&cachebuster="+cache_buster
                headers = {
                    "referrer": "https://www.monash.vic.gov.au/About-Us/Council/Council-Meetings/Agendas-Minutes",
                    "method": "GET",
                    "authority": "www.monash.vic.gov.au",
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "accept-language": "en-US,en;q=0.8",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                }
                cookie = {
                    cookie_on_a_diet['name']: cookie_on_a_diet['value']
                }
                data = requests.get(
                    url,
                    headers=headers,
                    cookies=cookie
                    )

                data_json = json.loads(data.text)

                data_soup = BeautifulSoup(data_json.get("html"), "html.parser")

                # find the date
                agenda_prefix = "Agenda of the Meeting of Monash Council held on "
                # Example: Agenda of the Meeting of Monash Council held on Tuesday 30 January 2024, from 7pm. 
                # We want, Tuesday 30 January 2024
                agenda_date = data_soup.find("div", class_="meeting-container").find_next("p").get_text()
                date_and_time = agenda_date[len(agenda_prefix):].split(",")[0]
                self.logger.info(f"Agenda date: {date_and_time}")
                meeting_titles = data_soup.find_all("div", class_="meeting-document-title")
                self.logger.info(f"Meeting titles:")
                for title in meeting_titles:
                    t = title.text.strip()
                    name.append(t)
                    self.logger.info(f"{t}")
                agendas = data_soup.find_all("div", class_="alt-formats")
                self.logger.info(f"Agenda Links:")
                for link in agendas:
                    agenda_link = self.base_url+link.find_next("a").get("href")
                    download_url.append(agenda_link)
                    self.logger.info(f"Link: {agenda_link}")                    

                if date_and_time:
                    date_match = self.date_pattern.search(date_and_time)
                    # Extract the matched date
                    if date_match:
                        extracted_date = date_match.group()
                        self.logger.info(f"Extracted Date: {extracted_date}")
                        date = extracted_date
                    else:
                        self.logger.warning("No date found in the input string.")

                    time_match = self.time_pattern.search(date_and_time)

                    # Extract the matched time
                    if time_match:
                        extracted_time = time_match.group()
                        self.logger.info(f"Extracted Date: {extracted_time}")
                        time = extracted_time
                    else:
                        self.logger.warning("No time found in the input string.")

            else:
                self.logger.error("couldn't find article")
                return None
            
        else:
            self.logger.error("Found nothing, did the webpage change?")
            return None

        scraper_return = ScraperReturn(name, date, time, self.base_url, download_url)

        self.logger.info(f"""
           Name: {scraper_return.name}
           Date: {scraper_return.date}
           Time: {scraper_return.time}
        BaseURI: {scraper_return.webpage_url}
    DownloadURI: {scraper_return.download_url}"""
        )
        self.logger.info(f"{self.council_name} scraper finished successfully")
        return scraper_return
        # return None


if __name__ == "__main__":
    scraper = MonashScraper()
    scraper.scraper()
