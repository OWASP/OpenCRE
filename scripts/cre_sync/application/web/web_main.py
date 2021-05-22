import json
import os
from pprint import pprint

from flask import Flask, abort, jsonify, send_from_directory, render_template, request, Blueprint
from jinja2 import Template, TemplateNotFound

from application import create_app
from application.database import db

ITEMS_PER_PAGE = 20

app= Blueprint('web', __name__, static_folder='../frontend/www')
database = db.Standard_collection()

@app.route("/rest/v1/id/<creid>", methods=["GET"])
def find_by_id(creid):  # refer
    cre = database.get_CRE(external_id=creid)
    if cre:
        return jsonify(cre.todict())
    abort(404)


@app.route("/rest/v1/name/<crename>", methods=["GET"])
def find_by_name(crename):
    cre = database.get_CRE(name=crename)
    if cre:
        return jsonify(cre.todict())
    abort(404)


@app.route("/rest/v1/standard/<sname>", methods=["GET"])
def find_standard_by_name(sname):
    opt_section = request.args.get("section")
    opt_subsection = request.args.get("subsection")
    opt_hyperlink = request.args.get("hyperlink")
    page = request.args.get("page") or 0
    items_per_page = request.args.get("items_per_page") or ITEMS_PER_PAGE

    total_pages, standards, _ = database.get_standards_with_pagination(
        name=sname, section=opt_section, subsection=opt_subsection, link=opt_hyperlink,
        page=int(page), items_per_page=int(items_per_page))
    result = {}
    result['total_pages'] = total_pages
    result['page'] = page
    if standards:
        res = [stand.todict() for stand in standards]
        result['standards'] = res
        return jsonify(result)
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


# If no other routes are matched, serve the react app, or any other static files (like bundle.js)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == "__main__":
    app.run(use_reloader=False, debug=False)
