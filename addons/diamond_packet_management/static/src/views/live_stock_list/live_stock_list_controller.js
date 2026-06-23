/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { onMounted, onPatched, useRef } from "@odoo/owl";

export class LiveStockListController extends ListController {
    static template = "diamond_packet_management.LiveStockListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.barcodeInputRef = useRef("barcodeInput");

        const focusInput = () => {
            // Only steal focus if nothing else is intentionally focused.
            const active = document.activeElement;
            const tag = active ? active.tagName.toLowerCase() : "";
            if (!active || tag === "body" || tag === "div") {
                this.barcodeInputRef.el?.focus();
            }
        };

        onMounted(focusInput);
        // Re-focus after every patch (re-render after scan / selection change).
        onPatched(() => {
            this.barcodeInputRef.el?.focus();
        });
    }

    /**
     * Override Odoo's default behaviour: keep the barcode scan bar (layout-actions slot)
     * visible even when records are selected.  The base class hides it via
     *   layoutActions: !this.hasSelectedRecords
     * which causes the barcode input to disappear on the first scan.
     */
    get display() {
        const base = super.display;
        if (!base.controlPanel) {
            return base;
        }
        return {
            ...base,
            controlPanel: {
                ...base.controlPanel,
                layoutActions: true,   // always show the scan bar
            },
        };
    }

    get className() {
        const base = this.props.className || "";
        return `${base} o_diamond_live_stock_list`.trim();
    }

    /**
     * Group header buttons as Issue | Receive pairs for the action bar.
     */
    get liveStockActionButtonGroups() {
        const buttons = (this.archInfo.headerButtons || []).filter(
            (button) => button.display !== "always" && !this.evalViewModifier(button.invisible)
        );
        const findButton = (predicate) => buttons.find((button) => predicate(button));

        const groups = [
            {
                cssClass: "o_diamond_action_group o_diamond_action_group_primary",
                buttons: [
                    findButton((b) => (b.string || "").includes("Issue Packet")),
                    findButton((b) => (b.string || "").includes("Receive Packet")),
                    findButton((b) => b.clickParams?.name === "action_open_issue_correction"),
                ],
            },
            {
                cssClass: "o_diamond_action_group",
                buttons: [
                    findButton((b) => b.clickParams?.name === "action_issue_process"),
                    findButton((b) => b.clickParams?.name === "action_receive_process"),
                ],
            },
            {
                cssClass: "o_diamond_action_group",
                buttons: [
                    findButton((b) => b.clickParams?.name === "action_issue_factory"),
                    findButton((b) => b.clickParams?.name === "action_receive_factory"),
                ],
            },
            {
                cssClass: "o_diamond_action_group",
                buttons: [
                    findButton((b) => b.clickParams?.name === "action_issue_jobwork"),
                    findButton((b) => b.clickParams?.name === "action_receive_jobwork"),
                ],
            },
            {
                cssClass: "o_diamond_action_group",
                buttons: [
                    findButton((b) => b.clickParams?.name === "action_issue_hpht"),
                    findButton((b) => b.clickParams?.name === "action_receive_hpht"),
                ],
            },
        ];
        return groups
            .map((group) => ({
                ...group,
                buttons: group.buttons.filter(Boolean),
            }))
            .filter((group) => group.buttons.length);
    }

    onBarcodeKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this._onBarcodeScan();
    }

    async _onBarcodeScan() {
        const input = this.barcodeInputRef.el;
        if (!input) {
            return;
        }
        const code = input.value.trim().toUpperCase();
        input.value = "";
        input.focus();
        if (!code) {
            return;
        }

        const packetIds = await this.orm.call(
            "diamond.packet",
            "find_live_stock_by_barcode",
            [code]
        );
        if (!packetIds.length) {
            this.notification.add(
                _t("No live-stock packet found for barcode: %s", code),
                { type: "warning" }
            );
            input.focus();
            return;
        }

        await this._selectAndPromoteRecord(packetIds[0]);
        // Focus returns via onPatched, but set it immediately too.
        input.focus();
    }

    async _selectAndPromoteRecord(resId) {
        const root = this.model.root;
        if (root.isGrouped) {
            await this._selectGroupedRecord(resId);
        } else {
            await this._selectFlatRecord(resId);
        }
        this.render(true);
    }

    async _selectFlatRecord(resId) {
        const root = this.model.root;
        let record = root.records.find((r) => r.resId === resId);
        if (!record) {
            record = await root.addExistingRecord(resId, true);
        } else {
            const idx = root.records.indexOf(record);
            if (idx > 0) {
                root.records.splice(idx, 1);
                root.records.unshift(record);
            }
        }
        record.toggleSelection(true);
    }

    async _selectGroupedRecord(resId) {
        const root = this.model.root;
        for (const group of root.groups) {
            let record = group.records.find((r) => r.resId === resId);
            if (record) {
                if (group.isFolded) {
                    await group.toggle();
                }
                const idx = group.records.indexOf(record);
                if (idx > 0) {
                    group.records.splice(idx, 1);
                    group.records.unshift(record);
                }
                const groupIdx = root.groups.indexOf(group);
                if (groupIdx > 0) {
                    root.groups.splice(groupIdx, 1);
                    root.groups.unshift(group);
                }
                record.toggleSelection(true);
                return;
            }
        }

        const groupByField = root.groupBy[0].split(":")[0];
        const fields = [groupByField];
        const [data] = await this.orm.searchRead(
            "diamond.packet",
            [["id", "=", resId]],
            fields,
            { limit: 1 }
        );
        if (!data) {
            this.notification.add(_t("Packet not found in the current list."), {
                type: "warning",
            });
            return;
        }

        const rawValue = data[groupByField];
        const groupValue = Array.isArray(rawValue) ? rawValue[0] : rawValue;
        let targetGroup = root.groups.find((g) => g.value === groupValue);
        if (!targetGroup) {
            targetGroup = root.groups.find(
                (g) => g.value === false && (groupValue === false || groupValue == null)
            );
        }
        if (!targetGroup) {
            this.notification.add(_t("Packet is not visible with the current filters."), {
                type: "warning",
            });
            return;
        }

        if (targetGroup.isFolded) {
            await targetGroup.toggle();
        }
        const record = await targetGroup.addExistingRecord(resId, true);
        const groupIdx = root.groups.indexOf(targetGroup);
        if (groupIdx > 0) {
            root.groups.splice(groupIdx, 1);
            root.groups.unshift(targetGroup);
        }
        record.toggleSelection(true);
    }
}
