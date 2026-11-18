<script setup lang="ts">
import { IconActivity, IconBrandGithub, IconInfoCircle, IconMoon, IconSun } from '@tabler/icons-vue';
import { useJobStore } from '@/stores/job.store';
import { useStyleStore } from '@/stores/style.store';

const styleStore = useStyleStore();
const jobStore = useJobStore();
const { isDarkTheme } = toRefs(styleStore);
</script>

<template>
  <c-tooltip :tooltip="$t('home.nav.github')" position="bottom">
    <c-button
      circle
      variant="text"
      href="https://github.com/datlt4/it-tools"
      target="_blank"
      rel="noopener noreferrer"
      :aria-label="$t('home.nav.githubRepository')"
    >
      <n-icon size="25" :component="IconBrandGithub" />
    </c-button>
  </c-tooltip>

  <c-tooltip tooltip="Job backend (tiến độ / hủy / tạm dừng)" position="bottom">
    <n-badge :value="jobStore.activeCount" :show="jobStore.activeCount > 0" type="info">
      <c-button circle variant="text" aria-label="Backend jobs" @click="jobStore.openDrawer()">
        <n-icon size="25" :component="IconActivity" />
      </c-button>
    </n-badge>
  </c-tooltip>
  <JobCenter />

  <c-tooltip :tooltip="$t('home.nav.about')" position="bottom">
    <c-button circle variant="text" to="/about" :aria-label="$t('home.nav.aboutLabel')">
      <n-icon size="25" :component="IconInfoCircle" />
    </c-button>
  </c-tooltip>
  <c-tooltip :tooltip="isDarkTheme ? $t('home.nav.lightMode') : $t('home.nav.darkMode')" position="bottom">
    <c-button circle variant="text" :aria-label="$t('home.nav.mode')" @click="() => styleStore.toggleDark()">
      <n-icon v-if="isDarkTheme" size="25" :component="IconSun" />
      <n-icon v-else size="25" :component="IconMoon" />
    </c-button>
  </c-tooltip>
</template>

<style lang="less" scoped>
.n-button {
  &:not(:last-child) {
    margin-right: 5px;
  }
}

// n-badge bọc nút Job: giữ cùng hàng, căn giữa như các nút circle khác
:deep(.n-badge) {
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
  margin-right: 5px;
  line-height: 1;
}
</style>
