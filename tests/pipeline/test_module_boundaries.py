"""13.7.1 — module boundaries and compatibility imports for the core pipeline."""

from __future__ import annotations

from pathlib import Path


def test_plan_submodules_keep_the_existing_public_import_surface() -> None:
    from app.pipeline import plan, plan_builder, plan_models, plan_planner, plan_rules

    assert plan.PlanDocument is plan_models.PlanDocument
    assert plan.PlanItem is plan_models.PlanItem
    assert plan.read_plan is plan_models.read_plan
    assert plan.OperationSource is plan_rules.OperationSource
    assert plan.select_operation is plan_rules.select_operation
    assert plan.create_plan is plan_builder.create_plan
    assert plan._Planner is plan_planner._Planner
    assert len(Path(plan.__file__).read_text(encoding="utf-8").splitlines()) <= 250


def test_executor_submodules_keep_the_existing_public_import_surface() -> None:
    from app.pipeline import execute, execute_errors, execute_images, execute_pdf, execute_types

    assert execute.EXECUTION_ERRORS is execute_errors.EXECUTION_ERRORS
    assert execute.SourceIntegrityError.__module__ == "app.pipeline.execute"
    assert execute.ExecutedItem is execute_types.ExecutedItem
    assert execute.ItemDecision is execute_types.ItemDecision
    assert execute.execute_extract is execute_pdf.execute_extract
    assert execute.execute_merge is execute_pdf.execute_merge
    assert execute.execute_wrap_image is execute_images.execute_wrap_image
    assert execute.execute_extract_image is execute_images.execute_extract_image
    assert execute.execute_render_image is execute_images.execute_render_image
    assert len(Path(execute.__file__).read_text(encoding="utf-8").splitlines()) <= 700
