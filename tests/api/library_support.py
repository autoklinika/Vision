"""Synthetic owned library for API-03 tests; never used by station composition."""
from copy import deepcopy
from vision_modules.ecu_library_backend import ECULibraryService

LIBRARY_ID = "api03_synthetic_library"
PROFILE_ID = "api03_synthetic"


def library_fixture(root):
    service = ECULibraryService(root)
    first = service.create_draft("ETC3", "provisional_3connector", "v1",
                                 PROFILE_ID, "r1", "API-03 synthetic reference")
    document = deepcopy(first["profile"])
    document["physical_states"] = [{"state_id": "closed", "display_name": "Closed enclosure",
        "geometry_id": None, "required_recipe_ids": ["inspect"], "verified": False, "source_id": None}]
    document["inspection_workflows"]["recipes"] = [{"recipe_id": "inspect", "state_id": "closed",
        "scenario_ref": "inspection", "required_view_ids": [], "required_modules": [],
        "required_capabilities": [], "quality_policy_refs": [], "required_asset_ids": [],
        "approval_scope": "verify_identity"}]
    service.update_draft(PROFILE_ID, document, first["etag"])
    return service
