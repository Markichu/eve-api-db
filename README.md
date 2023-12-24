# Eve API DB

A WIP tool for helping me make ISK in Eve Online. This is a personal project, but I'm open sourcing it in case anyone else finds it useful.

## Description

This tool continually sources market data from [Eve's ESI](https://esi.evetech.net/ui/#/) and stores it into a local database. It also provides a REST API for interfacing using FastAPI. 

Currently this has methods for aggregating market data, determining items on the marked that can be reprocessed for a profit, and determining items that can be manufactured for a profit.

## Getting Started

### Dependencies

* Python 3 probably >3.9

* Postgresql database

### Setting it up

* Create a postgresql database and run schema.sql on it to create the schema structure.
* Download the most recent [SDE from CCP](https://developers.eveonline.com/resource/resources) and extract it to the sde folder. the fsd/bsd folder should be subfolders of sde.
* Create a venv with `python3 -m venv venv` and activate it with `source venv/bin/activate`
* Install the requirements with `pip install -r requirements.txt`
* Run `python3 sde_importer.py` to import the SDE into the database.  This will take a minute to process the yaml files.

### Executing program

* Start the FastAPI server with `uvicorn main:app --reload` (docs can be found at http://localhost:8000/docs)
* Run the runner with `python3 runner.py` to start the background tasks.  This will continually make sure the database is up to date with the ESI.
* Run the _manufacturing.ipynb notebook to see an example of how to use the API to find profitable manufacturing items.


## Help

Currently under continuous refinement.  If you have any questions or suggestions, please open an issue.

## License

This project is licensed under the GPL-3.0 license - see the LICENSE file for details