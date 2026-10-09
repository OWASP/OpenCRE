# type: ignore
from __future__ import annotations

from typing import Any, Optional, Tuple

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

    @bp.route("/admin/agent/sync", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_agent_sync() -> Any:
        body = request.get_json(silent=True) or {}
        skip_nest = body.get("skip_nest")
        if skip_nest is not None:
            skip_nest = bool(skip_nest)
        wait = bool(body["wait"]) if "wait" in body else None
        try:
            return jsonify(
                service.start_agent_sync(
                    skip_nest=skip_nest,
                    skip_github=bool(body.get("skip_github", False)),
                    auto_concepts=bool(body.get("auto_concepts", True)),
                    wait=wait,
                )
            )
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("agent sync failed")
            return _err(500, f"agent sync failed: {exc}")

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
        cron = body.get("cron")
        try:
            return jsonify(
                service.expand_github_org_into_yaml(
                    yaml_text, owner, cron=str(cron) if cron is not None else None
                )
            )
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("expand org failed")
            return _err(500, f"expand org failed: {exc}")

    @bp.route("/admin/repos.yaml/add-repo", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_repos_yaml_add_repo() -> Any:
        body = request.get_json(silent=True) or {}
        yaml_text = body.get("yaml")
        if yaml_text is None:
            try:
                yaml_text = service.read_repos_yaml().get("yaml") or ""
            except FileNotFoundError as exc:
                return _err(404, _exc_message(exc))
        if not isinstance(yaml_text, str):
            return _err(400, "yaml must be a string")
        try:
            return jsonify(service.add_repository_to_yaml(yaml_text, body))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("add repo failed")
            return _err(500, f"add repo failed: {exc}")

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
        dry_run = bool(body["dry_run"]) if "dry_run" in body else False
        sync_repos = bool(body["sync_repos"]) if "sync_repos" in body else True
        skip_b = bool(body["skip_b"]) if "skip_b" in body else None
        skip_c = bool(body["skip_c"]) if "skip_c" in body else None
        wait = bool(body["wait"]) if "wait" in body else None
        max_repos: Optional[int]
        if "max_repos" in body and body["max_repos"] is not None:
            try:
                max_repos = int(body["max_repos"])
            except (TypeError, ValueError):
                return _err(400, "max_repos must be an integer")
            if max_repos < 1:
                return _err(400, "max_repos must be >= 1")
        else:
            max_repos = service.DEFAULT_OIE_MAX_REPOS
        try:
            result = service.start_ingestion(
                source=source or (str(target_id) if target_id else ""),
                target_id=str(target_id) if target_id else None,
                yaml_text=yaml_text if isinstance(yaml_text, str) else None,
                name=name,
                packaged=bool(body.get("packaged") or body.get("current")),
                dry_run=dry_run,
                sync_repos=sync_repos,
                max_repos=max_repos,
                skip_b=skip_b,
                skip_c=skip_c,
                wait=wait,
            )
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("ingest start failed")
            return _err(500, f"ingest start failed: {exc}")
        return jsonify(result)

    @bp.route("/admin/dashboard", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_dashboard() -> Any:
        try:
            return jsonify(service.dashboard_payload())
        except Exception as exc:
            logger.exception("dashboard failed")
            return _err(500, f"dashboard failed: {exc}")

    @bp.route("/admin/pipeline", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_pipeline() -> Any:
        try:
            return jsonify(service.pipeline_snapshot())
        except Exception as exc:
            logger.exception("pipeline snapshot failed")
            return _err(500, f"pipeline failed: {exc}")

    @bp.route("/admin/oie/rq/status", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_oie_rq_status() -> Any:
        """RQ depths + recent oie:* jobs (import-dashboard style)."""
        try:
            from application.utils.rq_dashboard_snapshot import (
                oie_rq_status,
                oie_run_queue_counts,
            )

            limit = max(1, min(int(request.args.get("limit") or 40), 200))
            body = oie_rq_status(limit=limit)
            run_id = (request.args.get("run_id") or "").strip()
            if run_id:
                from application.database import db as cre_db

                body["run"] = {
                    "run_id": run_id,
                    "counts": oie_run_queue_counts(
                        cre_db.Node_collection().session, run_id
                    ),
                }
            return jsonify(body)
        except Exception as exc:
            logger.exception("oie rq status failed")
            return _err(500, f"oie rq status failed: {exc}")

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

    @bp.route("/admin/imports/runs/<run_id>/links", methods=["GET"])
    @login_required
    @imports_enabled
    def admin_run_links(run_id: str) -> Any:
        try:
            return jsonify(service.review_run_links(run_id))
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except ValueError as exc:
            return _err(400, _exc_message(exc))
        except Exception as exc:
            logger.exception("run links failed")
            return _err(500, f"run links failed: {exc}")

    @bp.route("/admin/imports/runs/<run_id>/links", methods=["POST"])
    @login_required
    @imports_enabled
    def admin_review_link(run_id: str) -> Any:
        body = request.get_json(silent=True) or {}
        if "op_index" not in body or not body.get("action"):
            return _err(400, "op_index and action are required")
        try:
            link_index = body.get("link_index")
            return jsonify(
                service.review_link(
                    run_id,
                    op_index=int(body["op_index"]),
                    action=str(body.get("action") or ""),
                    link_index=int(link_index) if link_index is not None else None,
                    cre=body.get("cre") if isinstance(body.get("cre"), dict) else None,
                )
            )
        except KeyError as exc:
            return _err(404, _exc_message(exc))
        except (ValueError, IndexError, TypeError) as exc:
            return _err(400, _exc_message(exc))

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
