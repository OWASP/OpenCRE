# How to import a single standard from a CSV

This is a development guide, if you want to import you standard as a user please use MyOpenCRE
This guide assumes you have already installed OpenCRE

## Set Environment Variables
CRE uses environment variables to control how importing is done.
By default when a standard gets imported it will have embeddings generated from its
various sections/subsections and gap analysis against every other standard performed.
You can turn these off by setting the following

```bash
export NO_GEN_EMBEDDINGS=1 # do not generate embeddings
 export OpenCRE_gspread_Auth=service_account # set gspread to work with a service account
export CRE_NO_CALCULATE_GAP_ANALYSIS=1 # do not calculate gap analysis
export CRE_ROOT_CSV_IMPORT_ONLY=["<the name of the standard as it appears on opencre.org>"] # only import the standards in this list, ignore everything else
```

## Setup helper docker containers

You need redis and neo4j for importing. 
You can set them up with:
` make docker-redis` and `make docker-neo4j`

## Run one or more workers

Redis needs worker instances to pick up the worker jobs.
You can do so with: `make start-worker`

## Run the main import
On another terminal, set the same environment variables, then run:
`python cre.py --add --from_spreadsheet <the spreadsheet you want to use>`
