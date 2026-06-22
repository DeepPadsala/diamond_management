/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { LiveStockListController } from "./live_stock_list_controller";

export const liveStockListView = {
    ...listView,
    Controller: LiveStockListController,
};

registry.category("views").add("diamond_live_stock_list", liveStockListView);
