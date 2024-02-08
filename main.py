import argparse, sys
import os.path
import importlib
from pathlib import Path
import logging
from logging.config import dictConfig
from functions import download_pdf, is_in_councils_args, read_pdf, parse_pdf, write_email, send_email
import database as db
from _dataclasses import Council
from base_scraper import scraper_registry
from logging_config import setup_logging
import logging

from dotenv import dotenv_values


config = dotenv_values(".env")


def dynamic_import_scrapers():
    # Define the root directory for your scrapers relative to this script
    scrapers_root = Path(__file__).parent / "scrapers"

    # Iterate over all .py files in the scrapers directory and subdirectories
    for path in scrapers_root.rglob("*.py"):
        # Skip __init__.py files
        if path.name == "__init__.py":
            continue

        # Convert the file path to a Python module path
        module_path = path.relative_to(Path(__file__).parent).with_suffix(
            ""
        )  # Remove the .py suffix
        module_name = ".".join(module_path.parts)

        # Check council is wanted
        if args.councils is not None and not is_in_councils_args(path.name, args.councils):
            logging.info(f"Skipping {module_name}")
            continue

        logging.info(f"Loading {module_name}")
        # Import the module
        importlib.import_module(module_name)


def processor(council_name, state, scraper_results, scraper_instance):
    # Assuming council_name matches with your council names, adjust as necessary
    council = Council(name=council_name, scraper=scraper_instance)
    if not scraper_results.download_url:
        logging.error(f"No link found for {council.name}.")
        return
    if db.check_url(scraper_results.download_url):
        logging.warning(f"Link already scraped for {council.name}.")
        return
    logging.info("Link scraped! Downloading PDF...")
    download_pdf(scraper_results.download_url, council.name)

    logging.info("PDF downloaded!")
    logging.info("Reading PDF into memory...")
    text = read_pdf(council.name)
    with open(f"files/{council.name}_latest.txt", "w", encoding="utf-8") as f:
        f.write(text)

    logging.info("PDF read! Parsing PDF...")
    parser_results = parse_pdf(council.regexes, text)

    email_to = config.get("GMAIL_ACCOUNT_RECEIVE", None)

    if email_to:
        logging.info("Sending email...")
        email_body = write_email(council, scraper_results, parser_results)

        send_email(
            email_to,
            f"New agenda: {council.name} {scraper_results.date} meeting",
            email_body,
        )

    logging.info("PDF parsed! Inserting into database...")
    db.insert(council, scraper_results, parser_results)
    print("Database updated!")

    if not config.get("SAVE_FILES", "0") == "1":
        (
            os.remove(f"files/{council.name}_latest.pdf")
            if os.path.exists(f"files/{council.name}_latest.pdf")
            else None
        )
        (
            os.remove(f"files/{council.name}_latest.txt")
            if os.path.exists(f"files/{council.name}_latest.txt")
            else None
        )

    logging.info(f"Finished with {council.name}.")


def run_scrapers():
    for scraper_name, scraper_instance in scraper_registry.items():
        logging.error(f"Running {scraper_instance.council_name} scraper")
        scraper_results = scraper_instance.scraper()
        council_name = scraper_instance.council_name
        state = scraper_instance.state
        if scraper_results:
            # Process the result
            processor(council_name, state, scraper_results, scraper_instance)
        else:
            logging.error(f"Something broke, {council_name} scraper returned 'None'")


def main():
    if not os.path.exists("./agendas.db"):
        db.init()

    run_scrapers()


if __name__ == "__main__":
    setup_logging(level="INFO")
    logging.getLogger().name = "YIMBY-Scraper"

    parser=argparse.ArgumentParser()
    parser.add_argument("--councils", help="CSV List of councils: --councils=monash,bayside_nsw")
    args=parser.parse_args()
    logging.debug(f"Command Line: {sys.argv}\ncouncils: {args.councils}")
    logging.info("YIMBY SCRAPER Start")
    dynamic_import_scrapers()
    main()
