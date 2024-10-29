# MyOpenCRE API

## Introduction

This user guide briefly describes how to use the REST API of the MyOpenCRE functionality.
MyOpenCRE allows OpenCRE users to modify the OpenCRE catalogue by importing their own standards and updating the resources.
It is ONLY usable by running OpenCRE locally.

You can do so by running the docker container with a local database like so:
```bash
mkdir creDB
docker run -ti -v `pwd`/creDB:/db:rw \
     -e CRE_ALLOW_IMPORT=1 \
     -e PROD_DATABASE_URL="sqlite:///db/db.sqlite" \
     -p 5000:5000 \
     ghcr.io/owasp/opencre/opencre:latest
```

Please note that the first time you run this it will take a while as it needs to mirror the remote CRE database.
Once the screen has stopped producing text, you can find CRE in `localhost:5000`

## Endpoints

MyOpenCRE consists of two endpoints. `Generate CSV template` and `Import`
The `Generate` endpoint is a GET request that downloads a CSV containing all the CREs that your local CRE instance knows about.
The `Import` endpoint is a POST request that allows you to import the above CSV containing extra information or changes.

### Generate CRE CSV

You can download this CSV from the CRE instance with the command:
```bash
    curl localhost:5000/rest/v1/cre_csv
```
This allows you to manipulate the CRE graph using any spreadsheet software you want.

### Import From CRE CSV

Once you have made appropriate modifications, you can re-import with:

```bash
curl -X POST http://localhost:5000/rest/v1/cre_csv_import -F "cre_csv=@your-csv-file.csv"
```

### CRE CSV Format

You can find an example of the CRE CSV below.
There a couple things you need to pay attention for.

#### Staggered CREs

In the example below, CRE: `111-111` being in the column CRE0 means it's a `root` CRE (has no parent).
Conversely CRE: `222-222` being in the column CRE1 means it's a child of `111-111` similarly for `333-333` being a child of `222-222`
If you wanted to add `444-444` which is a child of `111-111` you could add a line with `444-444` being in the column `CRE 1`

The current CRE hierarchy has 5 levels so expect CREs up to `CRE 5`

### Separators

While this is a CSV file, you might have noticed that several elements contain a vertical break `|` character.
This allows the authors of the csv to instruct the OpenCRE application what is each field.
For CRES, the format is: `cre-id|"Name of the CRE"` so in the example below, `111-111` has a name of `Hello`
For standards the format is only used in the header to denote what is each column.
So for the standard named: "My Policy", column 4 is the name of each section, column 5 is the id of each section/clause and column 6 is the hyperlink to that particular clause.

```csv
CRE 0,CRE 1,CRE 2,My Policy|name,My Policy|id,My Policy|hyperlink
111-111|Hello,,,"this is my policy section blah, linked to cre 111-111",1.1,https://example.com/1
,222-222|World,,"this is my policy section blah, linked to cre 222-222",2.2,https://example.com/2
,,333-333|Hey,"this is my policy section blah, linked to cre 333-333",3.3,https://example.com/3

```
