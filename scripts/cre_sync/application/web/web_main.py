import json
from pprint import pprint

from flask import Flask, abort, jsonify, render_template, request, Blueprint
from jinja2 import Template, TemplateNotFound

from application import create_app
from application.database import db

ITEMS_PER_PAGE = 20

app= Blueprint('web',__name__)
database = db.Standard_collection()

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
    page = request.args.get("page")
    standards = database.get_standards(
        name=sname, section=opt_section, subsection=opt_subsection, link=opt_hyperlink,
        page=page or 0, items_per_page=ITEMS_PER_PAGE
    )
    if standards:
        res = [stand.todict() for stand in standards]
        return jsonify(res)
    abort(404)


# TODO: (spyros) paginate
@app.route("/rest/v1/tags", methods=["GET"])
def find_document_by_tag(sname):
    tags = request.args.getlist("tag")
    documents = database.get_by_tags(tags)
    if documents:
        res = [doc.todict() for doc in documents]
        return jsonify(res)


@app.errorhandler(404)
def page_not_found(e):
    # Even though Flask logs it by default,
    # I prefer to have a logger dedicated to 404
    return 'Resource Not found', 404


if __name__ == "__main__":
    app.run(use_reloader=False, debug=False)
