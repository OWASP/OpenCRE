# type: ignore
from __future__ import annotations

from typing import Any, Tuple

from cre_logging import get_logger

logger = get_logger(__name__)

from flask import jsonify, request

from application.utils.admin_panel import service


def _err(status: int, description: str) -> Tuple[Any, int]:
    return jsonify({"description": description}), status


def _exc_message(exc: BaseException) -> str:
    if exc.args:
        return str(exc.args[0])
    return str(exc)


def register_admin_panel_routes(
    bp: Any, login_required: Any, imports_enabled: Any
) -> None:
    @bp.route("/admin/agent/status", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_agent_status() -> Any:
        try:
            return jsonify(service.agent_status())
        except Exception as exc:
            logger.exception("agent status failed")
            return _err(500, f"agent status failed: {exc}")

    @bp.route("/admin/config", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_config_get() -> Any:
        try:
            return jsonify(service.config_payload())
        except Exception as exc:
            logger.exception("config get failed")
            return _err(500, f"config failed: {exc}")

    @bp.route("/admin/config", methods=["PUT"])
    @login_required
    @imports_enabled
    def admin_config_put() -> Any:
        body = request.get_json(silent=True) or {}
        updates = body.get("updates")
        if not isinstance(updates, dict):
            return _err(400, "updates object required")
        result = service.config_put(updates)
        if result["rejected"] and not result["applied"]:
            return _err(400, "rejected keys: %s" % ",".join(result["rejected"]))
        return jsonify(result)

    @bp.route("/admin/targets", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_targets_list() -> Any:
        try:
            return jsonify({"targets": service.list_targets()})
        except Exception as exc:
            logger.exception("list targets failed")
            return _err(500, f"failed to list targets: {exc}")

    @bp.route("/admin/targets", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_targets_add() -> Any:
        body = request.get_json(silent=True) or {}
        tid = str(body.get("id") or "").strip()
        kind = str(body.get("kind") or "").strip()
        name = str(body.get("name") or tid).strip()
        if not tid or not kind:
            return _err(400, "id and kind are required")
        try:
            row = service.add_target(
                target_id=tid,
                kind=kind,
                name=name,
                spec=body.get("spec") if isinstance(body.get("spec"), dict) else {},
                enabled=bool(body.get("enabled", True)),
            )
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        return jsonify(row), 201

    @bp.route("/admin/targets/<target_id>", methods=["DELETE"])
    @login_required
    @imports_enabled
    def admin_targets_delete(target_id: str) -> Any:
        try:
            if not service.remove_target(target_id):
                return _err(404, "target not found")
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        return jsonify({"deleted": target_id})

    @bp.route("/admin/repos.yaml", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_repos_yaml_get() -> Any:
        try:
            return jsonify(service.read_repos_yaml())
        except FileNotFoundError as exc:
            return _err(404, _exc_message(exc))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("repos.yaml get failed")
            return _err(500, f"repos.yaml get failed: {exc}")

    @bp.route("/admin/repos.yaml", methods=["PUT"])
    @login_required
    @imports_enabled
    def admin_repos_yaml_put() -> Any:
        body = request.get_json(silent=True) or {}
        yaml_text = body.get("yaml")
        if not isinstance(yaml_text, str):
            return _err(400, "yaml string required")
        try:
            return jsonify(service.write_repos_yaml(yaml_text))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("repos.yaml save failed")
            return _err(500, f"repos.yaml save failed: {exc}")

    @bp.route("/admin/repos.yaml/expand-org", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_repos_yaml_expand_org() -> Any:
        body = request.get_json(silent=True) or {}
        yaml_text = body.get("yaml")
        if yaml_text is None:
            yaml_text = ""
        if not isinstance(yaml_text, str):
            return _err(400, "yaml must be a string")
        owner = str(body.get("owner") or body.get("org") or "").strip()
        try:
            return jsonify(service.expand_github_org_into_yaml(yaml_text, owner))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("expand org failed")
            return _err(500, f"expand org failed: {exc}")

    @bp.route("/admin/ingest/start", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_ingest_start() -> Any:
        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or "").strip()
        target_id = body.get("target_id")
        yaml_text = body.get("yaml")
        if yaml_text is not None and not isinstance(yaml_text, str):
            return _err(400, "yaml must be a string")
        name = str(body.get("name") or "").strip() or None
        try:
            result = service.start_ingestion(
                source=source or (str(target_id) if target_id else ""),
                target_id=str(target_id) if target_id else None,
                yaml_text=yaml_text if isinstance(yaml_text, str) else None,
                name=name,
            )
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("ingest start failed")
            return _err(500, f"ingest start failed: {exc}")
        return jsonify(result)

    @bp.route("/admin/pipeline", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_pipeline() -> Any:
        try:
            return jsonify(service.pipeline_snapshot())
        except Exception as exc:
            logger.exception("pipeline snapshot failed")
            return _err(500, f"pipeline failed: {exc}")

    @bp.route("/admin/imports/runs/<run_id>/mapping", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_edit_mapping(run_id: str) -> Any:
        body = request.get_json(silent=True) or {}
        if "op_index" not in body or "after" not in body:
            return _err(400, "op_index and after are required")
        try:
            result = service.edit_staged_mapping(
                run_id, int(body["op_index"]), body["after"]
            )
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except (ValueError, IndexError, TypeError) as exc:
            return _err(400, _exc_message(exc))
        return jsonify(result)

    @bp.route("/admin/imports/drop-last", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_drop_last() -> Any:
        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or "").strip()
        if not source:
            return _err(400, "source is required")
        try:
            result = service.drop_last_ingestion(source)
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except PermissionError as exc:
            return _err(409, _exc_message(exc))
        return jsonify(result)
