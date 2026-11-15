# pxojdumper: provenance and changes

pxojdumper is a renamed distribution of tatuhack/Zygisk-Il2CppDumper,
commit ce531f9b4a53a37b1691d008f93caa8b339ee8c4:
https://github.com/tatuhack/Zygisk-Il2CppDumper/tree/ce531f9b4a53a37b1691d008f93caa8b339ee8c4

That repository is a fork of https://github.com/codehasan/Zygisk-Il2CppDumper,
which credits Perfare's original https://github.com/Perfare/Zygisk-Il2CppDumper.
Original copyright and author notices are preserved. This is not an independently
invented dumping engine, an official upstream release, or an endorsement by its authors.

Changes made 2026-11-15: display name, module/library identifiers, application
namespace, log tag, header guards, target-property prefix, and documentation.
The original runtime implementation, Zygisk API and xDL implementation are unchanged.
Upstream update delivery is disabled so it cannot overwrite this renamed build.
License and attribution files are now explicitly included in module packaging.
No protection-evasion features have been added.

The target property is now persist.pxojdumper.package (fallback:
debug.pxojdumper.package). Old properties are not read. The module ID is now
pxojdumper; this does not migrate/remove an older installation. Avoid enabling
both modules simultaneously on the same target.

See LICENSE, THIRD_PARTY_NOTICES.txt, and licenses/Apache-2.0.txt.
