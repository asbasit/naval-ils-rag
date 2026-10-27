# Engineering change impact assessment: EC-DEMO-001

**Replace obsolete power supply unit in the navigation radar transceiver**

- Platform: Arctic and Offshore Patrol Ship class (illustrative)
- System: Navigation radar, transceiver cabinet

The transceiver power supply unit is no longer manufactured. The equipment
supplier offers a replacement unit with the same mounting and connectors but a
different part number. The new unit has a higher predicted MTBF and adds a
built-in test indicator, which changes one periodic check from a voltage
measurement to a visual BIT check. No software change. The supplier has not
yet confirmed whether the new unit's capacitor bank needs special handling.

## Change characteristics

| Characteristic | Answer |
|---|---|
| New or changed part number, supplier or source of supply | yes |
| Change to physical form, mounting, interfaces, or how the item performs its function | no |
| Expected change in failure rate, MTBF, failure modes or redundancy | yes |
| Preventive or corrective maintenance tasks added, removed or changed | yes |
| Software or firmware change | no |
| New or changed tools, support and test equipment, or calibration needs | no |
| Change to how the crew operates the system | no |
| Change to power, cooling, space or weight demands on the ship | no |
| New or changed hazardous materials (batteries, chemicals, pressurized items) | **unknown** |
| Change driven by obsolescence or diminishing manufacturing sources | yes |
| Safety-related change or new hazards to personnel or equipment | **unknown** |
| New skills, qualifications or manning needs | no |

## Affected ILS products (13)

| # | ILS product | ILS element | Because | Action | Basis |
|---|---|---|---|---|---|
| 1 | Configuration records: configuration items, baseline and status accounting | Configuration management (DAOD 3034-0) | every engineering change | Raise or update the configuration change record; update the configuration item list and as-maintained baseline; record status accounting for every affected hull. | [1] |
| 2 | Support solution verification and validation | Product support management | every engineering change | Plan verification and validation of the updated support solution before the modified system returns to service. | [2] |
| 3 | Materiel assurance: safety and fit-for-purpose assessment | Sustaining engineering | part_number | Document that the changed item remains safe, fit for purpose, available and serviceable; confirm the new part is genuine and conforming. | [3] [4] |
| 4 | Logistic support analysis records: FMECA, maintenance task analysis, LORA | Maintenance management | part_number, reliability, maintenance_tasks | Update the LSA records for the changed item: failure modes and criticality, maintenance task analysis, and level-of-repair decision. | [5] |
| 5 | Reliability, availability and maintainability predictions and RBDs | Design influence | reliability, part_number | Rerun the reliability prediction and reliability block diagram for the affected function; check availability targets still hold. | [6] |
| 6 | Maintenance plan, preventive maintenance schedule and instructions | Maintenance management | maintenance_tasks, part_number, reliability | Revise the maintenance plan and preventive maintenance schedule: tasks, intervals (hours, calendar or mission), references and remarks. | [7] [8] |
| 7 | Maintenance management system task data (ERP) | Maintenance management | maintenance_tasks | Update task data in the maintenance management system at the same time as the instruction is released, so scheduled work matches the published procedure. | [9] |
| 8 | Spares and provisioning: sparing analysis, provisioning lists, codification | Supply support | part_number, reliability, obsolescence | Rerun the sparing analysis; update provisioning and initial spares lists; request codification of the new part; plan disposal or use of superseded stock. | [10] [11] |
| 9 | Obsolescence management plan | Sustaining engineering | obsolescence, part_number | Record the obsolescence case and resolution; check other items from the same source for similar risk. | [12] |
| 10 | Technical data: maintenance and operator manuals, parts lists, instructions | Technical data | part_number, maintenance_tasks | Identify every publication that shows the changed item (manuals, illustrated parts lists, maintenance instructions) and raise amendments. | [13] [14] |
| 11 | Safety precautions, warnings and tag-out steps in procedures | Technical data | maintenance_tasks | Review warnings, cautions and isolation (tag-out) steps in each affected procedure. | [15] [16] |
| 12 | Training and training support material | Training and training support | maintenance_tasks | Update operator and maintainer training packages and assess whether a training gap analysis is needed. | [17] |
| 13 | Packaging, handling, storage and transportation | Logistics-related operations | part_number | Update packaging, handling, storage and transport data for the new item, including any hazardous-goods requirements. | [18] |

## Open questions for the EC team (2)

Unknown answers in the change request, and the ILS products whose scope depends on each:

- **New or changed hazardous materials (batteries, chemicals, pressurized items)?** Bears on: Materiel assurance: safety and fit-for-purpose assessment (affected); Safety precautions, warnings and tag-out steps in procedures (affected); Packaging, handling, storage and transportation (affected).
- **Safety-related change or new hazards to personnel or equipment?** Bears on: Materiel assurance: safety and fit-for-purpose assessment (affected); Maintenance management system task data (ERP) (affected); Technical data: maintenance and operator manuals, parts lists, instructions (affected); Safety precautions, warnings and tag-out steps in procedures (affected).

## Not affected (4)

- Personnel: skills, qualifications and manning: none of its triggers apply (skills).
- Support and test equipment, tools and calibration: none of its triggers apply (tools_test_equipment).
- Computer resources: software support and cyber assurance: none of its triggers apply (software).
- Facilities and ship services: power, cooling, space and weight: none of its triggers apply (ship_services).

## Basis

1. **DAOD 3034-0, Configuration Management for Defence Systems** (DND/CAF) § Context: "…ughout its life cycle; - a defence system remains fit for purpose; - all configuration changes are methodically controlled and documented; and - unnecessary corrective actions, delays, low productivity and unmanageable p…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3034/3034-0-configuration-management-for-defence-systems.html#policy
2. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Requirements: "…and validated before: - introducing a new defence system into service; - modifying an in-service defence system and technology; - introducing solutions for in-service failures; - extending the life of an existing defence…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
3. **DAOD 3035-0, Materiel Assurance** (DND/CAF) § Requirements: "3.6 The DND and the CAF must establish materiel assurance that: - assesses and documents safety, fit for purpose, availability and serviceability of defence systems and equipment, and their level of compliance with appli…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3035/3035-0-materiel-assurance.html#pd
4. **DAOD 3035-0, Materiel Assurance** (DND/CAF) § Requirements: "…sition and support of authentic and conforming materiel by: - preventing counterfeit and non-conforming materiel from entering into the Defence Supply Chain; and - detecting, quarantining and eliminating counterfeit and…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3035/3035-0-materiel-assurance.html#pd
5. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.33: "…determine the basic information needed for applying the decision logic. The specific purpose of the FMEA is to determine the dominant failure modes and to determine the effects of each failure mode on the item where it…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
6. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…and activities throughout the life cycle of a defence system in order to achieve desired availability, serviceability and reliability at optimum life cycle cost. ILS uses a unified and iterative approach to: - cause supp…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
7. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.20: "…be Performed Column. When work is to be performed column shall show the frequency at which each function is to be performed, i.e., by hours of operation of the equipment, or by calendar time, or by mission and zone of o…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=20
8. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.18: "…can be classified as a component, equipment, subsystem, or system. 3.21 Periodicity. Delineates how frequently the maintenance requirement must be performed. 3.22 Protective device. Components, equipment, or design char…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
9. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.5: "…en a Maintenance Instruction change is identified for safety reasons the Technical Authority should ensure the ERP system is appropriately updated in advance or at the same time that the Maintenance Instruction is releas…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=5
10. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…aging, handling, storage and transportation; - maintenance management; - supply support; - product support management; - computer resources; - technical data; - design influence; - sustaining engineering; - facilities an…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
11. **NATO Logistics Handbook (1997), Ch. 10 Cooperative Logistics: ILS and codification** (NATO) : "…for, or support, the introduction of cooperative logistics arrangements. NATO Codification System (NCS) 1023. Every holder of materiel, whether to be manufacturer or user, requires a system to identify his equipment. For…"  
   https://web.archive.org/web/20201205121545id_/https://www.nato.int/docu/logi-en/1997/lo-1022.htm
12. **DAOD 3000-0, Materiel Acquisition and Support** (DND/CAF) § Requirements: "…information management requirements; - perform configuration management, obsolescence management and technological refresh throughout the life cycle of materiel; - increase federal contracting opportunities and access to…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3000/3000-0-materiel-acquisition-support.html#pol
13. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…- supply support; - product support management; - computer resources; - technical data; - design influence; - sustaining engineering; - facilities and infrastructure; - training and training support; - human resources a…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
14. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.19: "1. Preventive Maintenance Instructions shall contain the following sections in the order shown: 1. Les instructions de maintenance préventive doivent contenir les sections suivantes dans l’ordre indiqué: NOTE The prevent…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=19
15. **D-01-100-204/SF-000, Specification for Preventive Maintenance Instructions (Canadian Forces)** (DND/CAF) p.17: "…ons, soit 001, 002, 003, etc. Safety Requirements Mesures de sécurité 4. Any hazard or danger associated with installation of a part or equipment, or any safety or precautionary measure to be observed, shall be brought t…"  
   https://canadabuys.canada.ca/documents/pub/att/2022/01/24/1810cb1a22a31c0f65c386081abc39f1/d-01-100-204sf-000.pdf#page=17
16. **MIL-STD-3034A, Reliability-Centered Maintenance (RCM) Process** (USN) p.52: "…n or closed, when they are within the system boundary, and shall include tag-out action in the same step. When switches or valves are outside the system boundary, reference to the appropriate tag-out guidance (Tag-Out Us…"  
   https://everyspec.com/MIL-STD/MIL-STD-3000-9999/MIL-STD-3034A_50797/
17. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…influence; - sustaining engineering; - facilities and infrastructure; - training and training support; - human resources and personnel; and - support equipment."  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction
18. **DAOD 3007-0, Integrated Logistics Support** (DND/CAF) § Context: "…e functions, known as ILS elements: - logistics-related operations, i.e. packaging, handling, storage and transportation; - maintenance management; - supply support; - product support management; - computer resources; -…"  
   https://www.canada.ca/en/department-national-defence/corporate/policies-standards/defence-administrative-orders-directives/3000-series/3007/3007-0-integrated-logistics-support.html#introduction

---

Generated by naval-ils-rag `ec-impact` from public documents. Passages from NATO, USN sources describe that organization's practice, not RCN policy. This is a planning checklist, not an approved engineering or logistics decision.
