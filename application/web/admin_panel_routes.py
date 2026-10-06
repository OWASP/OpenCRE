# type: ignore
from __future__ import annotations

from typing import Any

from flask import abort, jsonify, request

from application.utils.admin_panel import service


def register_admin_panel_routes(
    bp: Any, login_required: Any, imports_enabled: Any
) -> None:
    @bp.route("/admin/agent/status", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_agent_status() -> Any:
        return jsonify(service.agent_status())

    @bp.route("/admin/config", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_config_get() -> Any:
        return jsonify(service.config_payload())

    @bp.route("/admin/config", methods=["PUT"])
    @login_required
    @imports_enabled
    def admin_config_put() -> Any:
        body = request.get_json(silent=True) or {}
        updates = body.get("updates")
        if not isinstance(updates, dict):
            abort(400, description="updates object required")
        result = service.config_put(updates)
        if result["rejected"] and not result["applied"]:
            abort(400, description="rejected keys: %s" % ",".join(result["rejected"]))
        return jsonify(result)

    @bp.route("/admin/targets", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_targets_list() -> Any:
        return jsonify({"targets": service.list_targets()})

    @bp.route("/admin/targets", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_targets_add() -> Any:
        body = request.get_json(silent=True) or {}
        tid = str(body.get("id") or "").strip()
        kind = str(body.get("kind") or "").strip()
        name = str(body.get("name") or tid).strip()
        if not tid or not kind:
            abort(400, description="id and kind are required")
        try:
            row = service.add_target(
                target_id=tid,
                kind=kind,
                name=name,
                spec=body.get("spec") if isinstance(body.get("spec"), dict) else {},
                enabled=bool(body.get("enabled", True)),
            )
        except ValueError as exc:
            abort(400, description=str(exc))
        return jsonify(row), 201

    @bp.route("/admin/targets/<target_id>", methods=["DELETE"])
    @login_required
    @imports_enabled
    def admin_targets_delete(target_id: str) -> Any:
        if not service.remove_target(target_id):
            abort(404, description="target not found")
        return jsonify({"deleted": target_id})

    @bp.route("/admin/ingest/start", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_ingest_start() -> Any:
        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or "").strip()
        target_id = body.get("target_id")
        try:
            result = service.start_ingestion(
                source=source or (str(target_id) if target_id else ""),
                target_id=str(target_id) if target_id else None,
            )
        except KeyError as exc:
            abort(404, description=str(exc))
        except ValueError as exc:
            abort(400, description=str(exc))
        return jsonify(result)

    @bp.route("/admin/pipeline", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_pipeline() -> Any:
        return jsonify(service.pipeline_snapshot())

    @bp.route("/admin/imports/runs/<run_id>/mapping", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_edit_mapping(run_id: str) -> Any:
        body = request.get_json(silent=True) or {}
        if "op_index" not in body or "after" not in body:
            abort(400, description="op_index and after are required")
        try:
            result = service.edit_staged_mapping(
                run_id, int(body["op_index"]), body["after"]
            )
        except KeyError as exc:
            abort(404, description=str(exc))
        except (ValueError, IndexError, TypeError) as exc:
            abort(400, description=str(exc))
        return jsonify(result)

    @bp.route("/admin/imports/drop-last", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_drop_last() -> Any:
        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or "").strip()
        if not source:
            abort(400, description="source is required")
        try:
            result = service.drop_last_ingestion(source)
        except KeyError as exc:
            abort(404, description=str(exc))
        except PermissionError as exc:
            abort(409, description=str(exc))
        return jsonify(result)
