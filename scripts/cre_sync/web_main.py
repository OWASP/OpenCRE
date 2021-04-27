import json
from database import db
from flask import Flask, jsonify, render_template, request
from jinja2 import Template
from pprint import pprint
from jinja2 import TemplateNotFound

app = Flask(__name__)

cache_loc = "standards_cache.sqlite"
database = db.Standard_collection(cache=True, cache_file=cache_loc)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/rest/v1/id/<creid>", methods=["GET"])
def find_by_id(creid):  # refer
    cre = database.get_CRE(id=creid)
    if cre:
        pprint(cre.todict())
        return jsonify(cre.todict())


@app.route("/rest/v1/name/<crename>", methods=["GET"])
def find_by_name(crename):
    cre = database.get_CRE(name=crename)
    if cre:
        pprint(cre.todict())
        return jsonify(cre.todict())


@app.route("/rest/v1/standard/<sname>", methods=["GET"])
def find_standard_by_name(sname):
    opt_section = request.args.get("section")
    opt_subsection = request.args.get("subsection")
    opt_hyperlink = request.args.get("hyperlink")

    standards = database.get_standards(
        name=sname, section=opt_section, subsection=opt_subsection, link=opt_hyperlink
    )
    if standards:
        res = [stand.todict() for stand in standards]
        return jsonify(res)


@app.route("/rest/v1/tags", methods=["GET"])
def find_document_by_tag(sname):
    tags = request.args.getlist("tag")
    documents = database.get_by_tags(tags)
    if documents:
        res = [doc.todict() for doc in documents]
        return jsonify(res)


if __name__ == "__main__":
    app.run(use_reloader=False, debug=False)
