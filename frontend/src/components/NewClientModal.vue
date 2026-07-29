<script setup>
import { ref, computed, watch, nextTick } from "vue";
import { store, closeNewClient, createClient } from "../store.js";
import { PURPOSES, CITIZENSHIP } from "../mocks/clients.js";
import { slugify } from "../utils.js";

const name = ref("");
const phone = ref("");
const email = ref("");
const purpose = ref("Purchase");
const citizenship = ref("US Citizen");
const amount = ref("");
const coOpen = ref(false);
const coName = ref("");
const coCitizenship = ref("US Citizen");
const ddOpen = ref(""); // which dropdown is open: "" | "purpose" | "citizenship" | "cocit"
const nameEl = ref(null);

const note = computed(() =>
  `Creates ~/MortgageWork/clients/${slugify(name.value.trim()) || "jane-doe"}/ · PROFILE.md + income/ assets/ credit/ ai/ · backed up automatically`);

watch(() => store.modalOpen, async open => {
  if (open) { await nextTick(); nameEl.value && nameEl.value.focus(); }
});

// Any outside click closes the dropdowns; a click on the dim area closes the modal
function overlayClick(e) {
  ddOpen.value = "";
  if (e.target === e.currentTarget) closeNewClient();
}

function toggleDd(which) {
  ddOpen.value = ddOpen.value === which ? "" : which;
}

function pickPurpose(p) {
  purpose.value = p;
  ddOpen.value = "";
}

function pickCitizenship(c) {
  citizenship.value = c;
  ddOpen.value = "";
}

function pickCoCitizenship(c) {
  coCitizenship.value = c;
  ddOpen.value = "";
}

function removeCo() {
  coOpen.value = false;
  coName.value = "";
  coCitizenship.value = "US Citizen";
}

function submit() {
  createClient({ name: name.value, phone: phone.value, email: email.value,
                 purpose: purpose.value, citizenship: citizenship.value, amount: amount.value,
                 co: coOpen.value ? { name: coName.value, citizenship: coCitizenship.value } : null });
}
</script>

<template>
  <div id="modal-overlay" v-show="store.modalOpen" @click="overlayClick">
    <div id="modal">
      <div class="m-head"><span>New Client</span><span class="x" @click="closeNewClient()">✕</span></div>
      <div class="add-form">
        <div class="full"><label>Full Name</label><input ref="nameEl" v-model="name" placeholder="Jane Doe"></div>
        <div><label>Phone</label><input v-model="phone" placeholder="(949) 555-0000"></div>
        <div><label>Email</label><input v-model="email" placeholder="jane@gmail.com"></div>
        <div><label>Purpose</label>
          <div class="dd">
            <button class="dd-btn" @click.stop="toggleDd('purpose')"><span>{{ purpose }}</span><span class="arr">▼</span></button>
            <div class="dd-menu" v-show="ddOpen === 'purpose'">
              <div v-for="p in PURPOSES" :key="p" class="dd-item" @click="pickPurpose(p)">{{ p }}</div>
            </div>
          </div>
        </div>
        <div><label>Citizenship</label>
          <div class="dd">
            <button class="dd-btn" @click.stop="toggleDd('citizenship')"><span>{{ citizenship }}</span><span class="arr">▼</span></button>
            <div class="dd-menu" v-show="ddOpen === 'citizenship'">
              <div v-for="c in CITIZENSHIP" :key="c" class="dd-item" @click="pickCitizenship(c)">{{ c }}</div>
            </div>
          </div>
        </div>
        <div class="full"><label>Target Amount</label><input v-model="amount" placeholder="$500,000"></div>
        <!-- Citizenship is per-borrower; co-borrower is optional at lead stage -->
        <div v-if="!coOpen" class="full"><span class="co-link" @click="coOpen = true">+ Add co-borrower</span></div>
        <template v-else>
          <div><label>Co-Borrower Name</label><input v-model="coName" placeholder="John Doe"></div>
          <div><label>Co-Borrower Citizenship</label>
            <div class="dd">
              <button class="dd-btn" @click.stop="toggleDd('cocit')"><span>{{ coCitizenship }}</span><span class="arr">▼</span></button>
              <div class="dd-menu" v-show="ddOpen === 'cocit'">
                <div v-for="c in CITIZENSHIP" :key="c" class="dd-item" @click="pickCoCitizenship(c)">{{ c }}</div>
              </div>
            </div>
          </div>
          <div class="full"><span class="co-link" @click="removeCo()">✕ Remove co-borrower</span></div>
        </template>
      </div>
      <div class="m-note">{{ note }}</div>
      <div class="m-foot">
        <button class="btn-sm" @click="closeNewClient()">Cancel</button>
        <button class="btn-sm primary" @click="submit()">Create Client</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
#modal-overlay {
  position: fixed; inset: 0; background: var(--scrim); z-index: 200;
  display: flex; align-items: center; justify-content: center;
}
#modal { width: 470px; background: var(--bg-panel); border: 1px solid var(--border-soft); }
#modal .m-head {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  display: flex; justify-content: space-between; align-items: center;
}
#modal .m-head .x { cursor: pointer; color: var(--text-4); font-size: 12px; }
#modal .m-head .x:hover { color: var(--red); }
/* Reuse add-form field styles, strip its box chrome inside the modal */
#modal .add-form { border: none; background: none; margin: 0; padding: 16px; }
#modal .m-note {
  padding: 10px 16px; border-top: 1px solid var(--border);
  font: 400 10px var(--mono); color: var(--text-4); line-height: 1.6;
}
#modal .m-foot {
  padding: 12px 16px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; justify-content: flex-end;
}
.co-link {
  font: 500 10px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-4); cursor: pointer; user-select: none;
}
.co-link:hover { color: var(--brand); }
</style>
