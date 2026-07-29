import { createApp } from "vue";
import App from "./App.vue";
import "./styles/global.css";
import { registerGlobals } from "./bridge.js";
import { showWelcome } from "./store.js";

// Window globals must exist before any v-html inline handler can fire
registerGlobals();
// Initial state: empty editor + daily briefing chat (sidebar shows the client list)
showWelcome();

createApp(App).mount("#app");
