/** @odoo-module **/

/**
 * Two client-action handlers for Diamond printing:
 *
 * 1. diamond_browser_print
 *    Fetches a PDF from /report/pdf/… and loads it in a hidden iframe.
 *    Reserved for future PDF reports — parent iframe.print() is blocked
 *    on ngrok after the async RPC.
 *
 * 2. diamond_browser_print_html  (barcode labels + jangad slips)
 *    Loads printable HTML in a hidden iframe.  The page itself calls
 *    window.print() on load — works through ngrok / remote URLs.
 */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// ── Shared helpers ────────────────────────────────────────────────────────────

function hiddenIframe() {
    const iframe = document.createElement("iframe");
    iframe.style.cssText =
        "position:fixed;top:0;left:0;width:0;height:0;border:none;visibility:hidden;";
    return iframe;
}

function scheduleCleanup(iframe, delayMs = 120000) {
    setTimeout(() => iframe.remove(), delayMs);
}

/**
 * Load label HTML in a hidden iframe.  Printing is handled by an inline
 * script inside the page (see barcode_labels_html.xml) so it works when
 * Odoo is accessed via ngrok — parent-window print() is blocked there
 * because the original button-click gesture expires during the RPC.
 */
function loadPrintPage(url) {
    return new Promise((resolve, reject) => {
        const iframe = hiddenIframe();
        iframe.onload = () => {
            scheduleCleanup(iframe, 180000);
            resolve();
        };
        iframe.onerror = () => {
            iframe.remove();
            reject(new Error("Failed to load print page."));
        };
        document.body.appendChild(iframe);
        iframe.src = url;
    });
}

// ── Handler: HTML barcode labels ───────────────────────────────────────────────

async function diamondBrowserPrintHtml(env, action) {
    const { html_url: htmlUrl, next } = action.params || {};
    const notification = env.services.notification;
    const actionService = env.services.action;

    if (!htmlUrl) {
        notification.add(_t("Print failed: missing label URL."), { type: "danger" });
        return false;
    }

    try {
        await loadPrintPage(htmlUrl);
    } catch (err) {
        console.error("[diamond] HTML print failed:", err);
        notification.add(
            _t("Could not open the print dialog for barcode labels."),
            { type: "danger" }
        );
    }

    if (next) {
        if (next.type === "ir.actions.act_window_close") {
            return { type: "ir.actions.act_window_close" };
        }
        return actionService.doAction(next);
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("diamond_browser_print_html", diamondBrowserPrintHtml);

// ── Handler: PDF reports (Jangad) ──────────────────────────────────────────────

function buildReportUrl(reportName, docIds, data) {
    const ids = docIds.join(",");
    let url = `/report/pdf/${encodeURIComponent(reportName)}/${ids}`;
    if (data && Object.keys(data).length) {
        const encoded = encodeURIComponent(JSON.stringify(data));
        url += `?options=${encoded}&context=${encoded}`;
    }
    return url;
}

async function printPdfBlob(blob) {
    return new Promise((resolve, reject) => {
        const blobUrl = URL.createObjectURL(blob);
        const iframe = hiddenIframe();
        let printed = false;

        const cleanup = () => {
            scheduleCleanup(iframe);
            setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
        };

        iframe.onload = () => {
            if (printed) {
                return;
            }
            try {
                printed = true;
                iframe.contentWindow.focus();
                iframe.contentWindow.print();
                cleanup();
                resolve();
            } catch (err) {
                iframe.remove();
                URL.revokeObjectURL(blobUrl);
                reject(err);
            }
        };

        iframe.onerror = () => {
            iframe.remove();
            URL.revokeObjectURL(blobUrl);
            reject(new Error("Failed to load PDF for printing."));
        };

        document.body.appendChild(iframe);
        iframe.src = blobUrl;
    });
}

async function diamondBrowserPrint(env, action) {
    const { report_name: reportName, doc_ids: docIds, data, next } = action.params || {};
    const notification = env.services.notification;
    const actionService = env.services.action;

    if (!reportName || !docIds?.length) {
        notification.add(_t("Print failed: missing report data."), { type: "danger" });
        return next ? actionService.doAction(next) : false;
    }

    try {
        const url = buildReportUrl(reportName, docIds, data);
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        if (!blob.size) {
            throw new Error("Empty PDF");
        }
        await printPdfBlob(blob);
    } catch (err) {
        console.error("[diamond] PDF print failed:", err);
        notification.add(
            _t("Could not open print dialog. Check that the report generates a valid PDF."),
            { type: "danger" }
        );
    }

    if (next) {
        if (next.type === "ir.actions.act_window_close") {
            return { type: "ir.actions.act_window_close" };
        }
        return actionService.doAction(next);
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("diamond_browser_print", diamondBrowserPrint);
