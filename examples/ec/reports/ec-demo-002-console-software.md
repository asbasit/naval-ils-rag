# Engineering change impact assessment: EC-DEMO-002

**Operator console software update adding a new track-display mode**

- Platform: Joint Support Ship class (illustrative)
- System: Combat management system, operator consoles

A software release adds a track-display mode and changes two operator menus.
Loading the release needs a new maintenance laptop image. Hardware is
unchanged. Operators need familiarization on the new mode.

## Change characteristics

| Characteristic | Answer |
|---|---|
| New or changed part number, supplier or source of supply | no |
| Change to physical form, mounting, interfaces, or how the item performs its function | no |
| Expected change in failure rate, MTBF, failure modes or redundancy | no |
| Preventive or corrective maintenance tasks added, removed or changed | yes |
| Software or firmware change | yes |
| New or changed tools, support and test equipment, or calibration needs | yes |
| Change to how the crew operates the system | yes |
| Change to power, cooling, space or weight demands on the ship | no |
| New or changed hazardous materials (batteries, chemicals, pressurized items) | no |
| Change driven by obsolescence or diminishing manufacturing sources | no |
| Safety-related change or new hazards to personnel or equipment | no |
| New skills, qualifications or manning needs | no |

## Affected ILS products (10)

| # | ILS product | ILS element | Because | Action | Basis |
|---|---|---|---|---|---|
| 1 | Configuration records: configuration items, baseline and status accounting | Configuration management (DAOD 3034-0) | every engineering change | Raise or update the configuration change record; update the configuration item list and as-maintained baseline; record status accounting for every affected hull. | [1] |
| 2 | Support solution verification and validation | Product support management | every engineering change | Plan verification and validation of the updated support solution before the modified system returns to service. | [2] |
| 3 | Logistic support analysis records: FMECA, maintenance task analysis, LORA | Maintenance management | maintenance_tasks | Update the LSA records for the changed item: failure modes and criticality, maintenance task analysis, and level-of-repair decision. | [3] |
| 4 | Maintenance plan, preventive maintenance schedule and instructions | Maintenance management | maintenance_tasks, tools_test_equipment | Revise the maintenance plan and preventive maintenance schedule: tasks, intervals (hours, calendar or mission), references and remarks. | [4] [5] |
| 5 | Maintenance management system task data (ERP) | Maintenance management | maintenance_tasks | Update task data in the maintenance management system at the same time as the instruction is released, so scheduled work matches the published procedure. | [6] |
| 6 | Technical data: maintenance and operator manuals, parts lists, instructions | Technical data | maintenance_tasks, operator_procedure, software | Identify every publication that shows the changed item (manuals, illustrated parts lists, maintenance instructions) and raise amendments. | [7] [8] |
| 7 | Safety precautions, warnings and tag-out steps in procedures | Technical data | maintenance_tasks | Review warnings, cautions and isolation (tag-out) steps in each affected procedure. | [9] [10] |
| 8 | Training and training support material | Training and training support | operator_procedure, software, maintenance_tasks | Update operator and maintainer training packages and assess whether a training gap analysis is needed. | [11] |
| 9 | Support and test equipment, tools and calibration | Support equipment | tools_test_equipment | List new or changed tools and test equipment; provision them; add calibration requirements. | [12] [13] |
| 10 | Computer resources: software support and cyber assurance | Computer resources | software | Update the software configuration baseline and loading procedures; confirm cyber materiel assurance for platform technology. | [14] [15] |

## Not affected (7)

- Materiel assurance: safety and fit-for-purpose assessment: none of its triggers apply (safety, form_fit_function, hazardous_material, part_number).
- Reliability, availability and maintainability predictions and RBDs: none of its triggers apply (reliability, part_number).
- Spares and provisioning: sparing analysis, provisioning lists, codification: none of its triggers apply (part_number, reliability, obsolescence).
- Obsolescence management plan: none of its triggers apply (obsolescence, part_number).
- Personnel: skills, qualifications and manning: none of its triggers apply (skills).
- Facilities and ship services: power, cooling, space and weight: none of its triggers apply (ship_services).
- Packaging, handling, storage and transportation: none of its triggers apply (hazardous_material, form_fit_function, part_number).

## Basis

1. **DAOD 3034-0, Configuration Management for Defence Systems** (DND/CAF) § Context: "…ughout its life cycle; - a defence system remains fit for purpose; - all configuration changes are methodically controlled and documented; and - unnecessary corrective actions, delays, low productivity and unmanageable p…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3034/3034-0-configuration-management-for-defence-systems.html#policy
2. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Requirements: "…and validated before: - introducing a new defence system into service; - modifying an in-service defence system and technology; - introducing solutions for in-service failures; - extending the life of an existing defence…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
3. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.33: "…determine the basic information needed for applying the decision logic. The specific purpose of the FMEA is to determine the dominant failure modes and to determine the effects of each failure mode on the item where it…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
4. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.20: "…be Performed Column. When work is to be performed column shall show the frequency at which each function is to be performed, i.e., by hours of operation of the equipment, or by calendar time, or by mission and zone of o…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=20
5. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.18: "…can be classified as a component, equipment, subsystem, or system. 3.21 Periodicity. Delineates how frequently the maintenance requirement must be performed. 3.22 Protective device. Components, equipment, or design char…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
6. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.5: "…en a Maintenance Instruction change is identified for safety reasons the Technical Authority should ensure the ERP system is appropriately updated in advance or at the same time that the Maintenance Instruction is releas…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=5
7. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…- supply support; - product support management; - computer resources; - technical data; - design influence; - sustaining engineering; - facilities and infrastructure; - training and training support; - human resources a…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
8. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.19: "1. Preventive Maintenance Instructions shall contain the following sections in the order shown: 1. Les instructions de maintenance préventive doivent contenir les sections suivantes dans l’ordre indiqué: NOTE The prevent…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=19
9. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.17: "…ons, soit 001, 002, 003, etc. Safety Requirements Mesures de sécurité 4. Any hazard or danger associated with installation of a part or equipment, or any safety or precautionary measure to be observed, shall be brought t…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=17
10. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.52: "…n or closed, when they are within the system boundary, and shall include tag-out action in the same step. When switches or valves are outside the system boundary, reference to the appropriate tag-out guidance (Tag-Out Us…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
11. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…influence; - sustaining engineering; - facilities and infrastructure; - training and training support; - human resources and personnel; and - support equipment."  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
12. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…- training and training support; - human resources and personnel; and - support equipment."  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
13. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.49: "…comprehensive life-cycle support, encompassing acquisition, outfitting, calibration support, and retirement of GPETE, as well as calibration standards. This includes test equipment that has the potential for use in PMS.…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
14. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…aintenance management; - supply support; - product support management; - computer resources; - technical data; - design influence; - sustaining engineering; - facilities and infrastructure; - training and training suppor…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
15. **DAOD 3035-0, Materiel Assurance** (DND/CAF) § 2. Definitions: "…red without legal right. (Defence Terminology Bank record number 696291) cyber materiel assurance (cyber assurance du matériel) Assurance that a platform technology meets materiel cyber-resilience requirements. (Defence…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3035/3035-0-materiel-assurance.html#def

---

Generated by naval-ils-rag `ec-impact` from public documents. Passages from USN sources describe that organization's practice, not RCN policy. This is a planning checklist, not an approved engineering or logistics decision.
