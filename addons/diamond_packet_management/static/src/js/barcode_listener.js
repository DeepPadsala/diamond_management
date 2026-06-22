/** @odoo-module **/

/*
 * Global barcode-gun listener for the Diamond Packet Management app.
 *
 * USB barcode guns behave like keyboards: they type the barcode characters
 * very fast and finish with Enter. We watch for that pattern (>= 4 chars
 * typed in <= 100 ms apart followed by Enter) outside any input/textarea
 * and trigger a server lookup that opens the matching packet.
 *
 * Disabled when focus is in an input, textarea, or contenteditable
 * element so manual typing isn't hijacked.
 */

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const SCAN_TIMEOUT_MS = 100;     // max gap between chars
const MIN_LEN = 4;               // shortest accepted barcode

const diamondBarcodeService = {
    dependencies: ["action"],

    start(env, { action }) {
        let buffer = "";
        let lastKeyAt = 0;

        function isInEditable(target) {
            if (!target) return false;
            const tag = (target.tagName || "").toUpperCase();
            if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
            if (target.isContentEditable) return true;
            return false;
        }

        async function lookup(code) {
            const normalized = code.trim().toUpperCase();
            if (normalized.length < MIN_LEN) {
                return;
            }
            try {
                const res = await rpc("/web/dataset/call_kw", {
                    model: "diamond.packet",
                    method: "find_by_barcode",
                    args: [normalized],
                    kwargs: {},
                });
                const ids = Array.isArray(res) ? res : [];
                if (ids.length === 1) {
                    await action.doAction({
                        type: "ir.actions.act_window",
                        res_model: "diamond.packet",
                        res_id: ids[0],
                        views: [[false, "form"]],
                        target: "current",
                    });
                }
            } catch (err) {
                console.warn("[diamond] barcode lookup failed:", err);
            }
        }

        function isLiveStockList() {
            return Boolean(document.querySelector(".o_diamond_live_stock_list"));
        }

        document.addEventListener("keydown", (ev) => {
            if (isInEditable(ev.target)) return;
            if (isLiveStockList()) return;

            const now = Date.now();
            if (now - lastKeyAt > SCAN_TIMEOUT_MS) {
                buffer = "";
            }
            lastKeyAt = now;

            if (ev.key === "Enter") {
                if (buffer.length >= MIN_LEN) {
                    const code = buffer.trim();
                    buffer = "";
                    ev.preventDefault();
                    lookup(code);
                }
                return;
            }
            if (ev.key && ev.key.length === 1) {
                buffer += ev.key;
            }
        });

        return { lookup };
    },
};

registry.category("services").add("diamond_barcode_listener", diamondBarcodeService);
