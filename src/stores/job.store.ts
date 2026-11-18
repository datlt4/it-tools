import { defineStore } from 'pinia';
import type { ConverterJob } from '@/utils/converterApi';
import { cancelJob, deleteJob, jobDownloadUrl, listJobs, pauseJob, resumeJob } from '@/utils/converterApi';
import { downloadUrl } from '@/utils/media';

let pollTimer: ReturnType<typeof setInterval> | null = null;

const ACTIVE = ['queued', 'running', 'paused'];

export const useJobStore = defineStore('converter-jobs', {
  state: () => ({
    jobs: [] as ConverterJob[],
    drawerOpen: false,
    lastError: '' as string,
  }),
  getters: {
    activeCount: state => state.jobs.filter(j => ACTIVE.includes(j.status)).length,
    hasUnfinished(state): boolean {
      return state.jobs.some(j => ACTIVE.includes(j.status));
    },
  },
  actions: {
    openDrawer() {
      this.drawerOpen = true;
      void this.refresh();
    },
    track(id: string, name?: string) {
      if (!this.jobs.some(j => j.id === id)) {
        this.jobs.unshift({
          id, name: name ?? id, format: '', status: 'queued',
          progress: 0, created_at: Date.now() / 1000,
          error: null, out_filename: null, out_size: null,
        });
      }
      this.ensurePolling();
      void this.refresh();
    },
    ensurePolling() {
      if (pollTimer)
        return;
      pollTimer = setInterval(() => {
        void this.refresh().then(() => {
          if (!this.hasUnfinished && pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        });
      }, 1500);
    },
    async refresh() {
      try {
        const remote = await listJobs();
        const known = new Map(this.jobs.map(j => [j.id, j]));
        for (const r of remote) {
          if (!r.name && known.get(r.id)?.name)
            r.name = known.get(r.id)!.name;
        }
        this.jobs = remote;
        this.lastError = '';
      }
      catch (e: any) {
        this.lastError = e?.message ?? String(e);
      }
    },
    async pause(id: string) {
      this.patch(await pauseJob(id));
    },
    async resume(id: string) {
      this.patch(await resumeJob(id));
    },
    async cancel(id: string) {
      this.patch(await cancelJob(id));
    },
    async remove(id: string) {
      await deleteJob(id);
      this.jobs = this.jobs.filter(j => j.id !== id);
    },
    async clearFinished() {
      const done = this.jobs.filter(j => !ACTIVE.includes(j.status));
      await Promise.all(done.map(j => deleteJob(j.id)));
      const ids = new Set(done.map(j => j.id));
      this.jobs = this.jobs.filter(j => !ids.has(j.id));
    },
    patch(j: ConverterJob) {
      const i = this.jobs.findIndex(x => x.id === j.id);
      if (i !== -1)
        this.jobs[i] = { ...this.jobs[i], ...j };
      else this.jobs.unshift(j);
    },
    download(j: ConverterJob) {
      if (j.status !== 'done')
        return;
      downloadUrl(jobDownloadUrl(j.id), j.out_filename || `job-${j.id}`);
    },
  },
});
