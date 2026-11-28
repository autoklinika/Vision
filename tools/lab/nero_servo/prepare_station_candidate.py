"""Generate an immutable offline review candidate from archived station evidence."""
import argparse
import json
from pathlib import Path
from vision_station.nero_manual_station import prepare, decode, read_bounded
from vision_station.nero_joint_limits import InstalledJointLimits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","firmware","pose","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--mesh-source-root",type=Path)
    a=p.parse_args()
    if not all(x.is_absolute() and x.resolve().is_relative_to("/srv/vision-data")
               for x in (a.source,a.firmware,a.pose,a.output)):
        p.error("private NVMe artifacts only")
    if a.mesh_source_root is not None and not a.mesh_source_root.resolve().is_relative_to("/srv/vision-data"):
        p.error("mesh source must be on station NVMe")
    from ament_index_python.packages import get_package_share_directory
    mesh_root=Path(get_package_share_directory("agx_arm_description"))
    fw=decode(read_bounded(a.firmware))
    ref=InstalledJointLimits(a.source/"model.urdf",fw["source"]["firmwareProfile"])()
    if ref.sdk_version!=fw["source"]["sdkVersion"] or ref.sdk!=tuple(tuple(r) for r in fw["sdkRad"]):
        raise ValueError("installed SDK differs from recorded reference")
    candidate=prepare(a.source,a.firmware,a.pose,a.output,mesh_root=mesh_root,mesh_source_root=a.mesh_source_root)
    print(json.dumps(candidate.manifest,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
