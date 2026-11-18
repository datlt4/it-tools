<script setup lang="ts">
import { useJobStore } from '@/stores/job.store';
import { formatBytes } from '@/utils/convert';

const jobStore = useJobStore();

const statusLabel: Record<string, string> = {
  queued: 'Đang chờ',
  running: 'Đang chạy',
  paused: 'Tạm dừng',
  done: 'Xong',
  error: 'Lỗi',
  canceled: 'Đã hủy',
};

const statusType: Record<string, 'default' | 'info' | 'success' | 'error' | 'warning'> = {
  queued: 'default',
  running: 'info',
  paused: 'warning',
  done: 'success',
  error: 'error',
  canceled: 'default',
};

function pct(j: { progress: number }) {
  return Math.round((j.progress || 0) * 100);
}
</script>

<template>
  <n-drawer v-model:show="jobStore.drawerOpen" :width="480" placement="right">
    <n-drawer-content title="Tiến độ job (backend)" closable>
      <template #header>
        <div flex items-center gap-2>
          <span font-bold>Tiến độ job (backend)</span>
          <n-badge v-if="jobStore.activeCount" :value="jobStore.activeCount" type="info" />
        </div>
      </template>

      <div v-if="jobStore.lastError" mb-3>
        <c-alert type="warning">
          Không tới được backend: {{ jobStore.lastError }}
        </c-alert>
      </div>

      <div v-if="!jobStore.jobs.length" op-60 text-sm>
        Chưa có job nào. Vào Video converter → chọn "Backend job" để gửi việc nặng lên server, tiến độ hiện ở đây.
      </div>

      <div flex flex-col gap-3>
        <div v-for="j in jobStore.jobs" :key="j.id" border rounded p-3>
          <div flex items-center justify-between gap-2>
            <div truncate font-medium>
              {{ j.name }}
            </div>
            <n-tag size="small" :type="statusType[j.status] ?? 'default'">
              {{ statusLabel[j.status] ?? j.status }}
            </n-tag>
          </div>
          <div text-xs op-60 mt-1>
            {{ j.format.toUpperCase() }} • {{ pct(j) }}%
            <span v-if="j.out_size"> • {{ formatBytes(j.out_size) }}</span>
          </div>
          <n-progress type="line" :percentage="pct(j)" :status="j.status === 'error' ? 'error' : j.status === 'done' ? 'success' : 'default'" mt-2 />
          <div v-if="j.error" text-red-500 text-xs mt-1>
            {{ j.error }}
          </div>
          <div flex flex-wrap gap-2 mt-2>
            <c-button v-if="j.status === 'running'" size="small" @click="jobStore.pause(j.id)">
              Tạm dừng
            </c-button>
            <c-button v-if="j.status === 'paused'" size="small" type="primary" @click="jobStore.resume(j.id)">
              Tiếp tục
            </c-button>
            <c-button v-if="j.status === 'queued' || j.status === 'running' || j.status === 'paused'" size="small" @click="jobStore.cancel(j.id)">
              Hủy
            </c-button>
            <c-button v-if="j.status === 'done'" size="small" type="primary" @click="jobStore.download(j)">
              Tải xuống
            </c-button>
            <c-button v-if="j.status === 'done' || j.status === 'error' || j.status === 'canceled'" size="small" @click="jobStore.remove(j.id)">
              Xóa
            </c-button>
          </div>
        </div>
      </div>

      <template #footer>
        <div flex gap-2>
          <c-button size="small" @click="jobStore.refresh()">
            Làm mới
          </c-button>
          <c-button size="small" @click="jobStore.clearFinished()">
            Xóa job đã xong
          </c-button>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
