# Diamond Packet Management

A self-contained **Odoo 18** application for diamond packet lifecycle
management — masters, inward/outward, factory & jobwork issue/receive,
HPHT issue/receive, live stock dashboard, packet history, and
USB-barcode-gun support — built without depending on Odoo's `sale`,
`stock`, `purchase`, `account`, or `mrp` modules.

The only Odoo modules used are `base` (for `res.users` and
`res.company`) and `web` (for assets). All business models are custom
and prefixed with `diamond.`.

## Install

1. Drop this folder into your Odoo addons path, e.g.
   `/home/paython/Documents/diamond/diamond_addons/addons/diamond_packet_management`.
2. Add `/home/paython/Documents/diamond/diamond_addons/addons` to your
   `addons_path` in `odoo.conf`.
3. Restart Odoo, *Update Apps List*, search for **Diamond Packet
   Management**, and install.

## Multi-company

Each `res.company` gets its own dataset:

* Every model has a `company_id` field defaulted to `self.env.company`.
* Record rules restrict `read/write/create/unlink` to
  `('company_id', 'in', company_ids)`.
* Sequences are per-company so packet numbers won't collide between
  companies.
* Switching the company in the top bar instantly switches the dataset
  (just like the rest of Odoo).

## Modules / models

### Masters

| Model                        | Purpose                                  |
| ---------------------------- | ---------------------------------------- |
| `diamond.shape`              | Round, Princess, Oval, …                 |
| `diamond.color`              | D, E, F, G, …                            |
| `diamond.clarity`            | FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2   |
| `diamond.cut` / `polish` / `symmetry` | Cut, Polish, Symmetry grades    |
| `diamond.fluorescence`       | None, Faint, Medium, Strong, Very Strong |
| `diamond.lab`                | GIA, IGI, HRD, …                         |
| `diamond.charni`             | Sieve buckets                            |
| `diamond.process`            | Sarine, Cutting, Polish, HPHT, Cert, …   |
| `diamond.employee`           | Workforce master                         |
| `diamond.account.group`      | Account classification                   |
| `diamond.ledger`             | Customer / supplier / jobworker / HPHT   |
| `diamond.party.labour`       | Outside labour rates                     |
| `diamond.worker.labour`      | In-house labour rates                    |
| `diamond.price`              | Rapaport-style price grid                |
| `diamond.product`            | Rough / polished / mixed products        |

### Core

* **`diamond.packet`** — the unit of stock. Holds 4Cs + CPS + barcode +
  current location/holder/process + state machine.
* **`diamond.packet.history`** — immutable per-packet audit log
  (auto-created on every state/location change).

### Transactions

* `diamond.inward` / `diamond.outward` (header + line)
* `diamond.process.issue` / `diamond.process.receive`
* `diamond.jobwork.issue` / `diamond.jobwork.receive`
* `diamond.factory.issue` / `diamond.factory.receive`
* `diamond.hpht.issue` / `diamond.hpht.receive`

Each `_confirm` action mutates the packet's state and logs a history row.

## Barcode-gun support

Two layers:

1. **Wizard** — `Diamond → Utility → Scan Barcode (Gun)` opens an
   auto-focused input. The gun types the code + Enter, the wizard
   server-side searches `diamond.packet.barcode` and opens the matching
   packet form.
2. **Global keyboard listener** — `static/src/js/barcode_listener.js`
   detects scanner-style fast-typing-then-Enter outside any input
   element and silently RPCs `diamond.packet.find_by_barcode(code)`. If
   a single packet is returned the listener navigates straight to its
   form view. Manual typing into inputs is left untouched.

## Live Stock dashboard

`Diamond → Live Stock` reuses the packet list with
`state not in ('outward','closed')` and exposes:

* **Live Stock** — list / kanban filtered to in-flight packets.
* **Stock Tally** — pivot of pcs/cts/amount by Shape × Color × Clarity.
* **Manager Stock Tally** — same pivot grouped by Holder + Location.
* **HPHT Pending** — list of packets currently with HPHT vendors.

## Roles

* **User** — day-to-day operator (scan, inward, outward, issue/receive).
* **Manager** — adds master maintenance and override permissions.

## Layout

```
diamond_packet_management/
├── __init__.py
├── __manifest__.py
├── data/
│   ├── diamond_sequences.xml
│   └── diamond_demo_masters.xml
├── models/                ← all 25+ business models
├── security/
│   ├── diamond_security.xml
│   └── ir.model.access.csv
├── static/
│   ├── description/icon.png
│   └── src/js/barcode_listener.js
├── views/                 ← list, form, search, pivot, kanban
└── wizard/
    ├── barcode_search.py
    └── barcode_search_views.xml
```
