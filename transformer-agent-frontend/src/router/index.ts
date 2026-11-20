import { createRouter, createWebHistory } from 'vue-router';
import Upload from '../views/TenderAnalysis/Upload.vue';
import Review from '../views/TenderAnalysis/Review.vue';
import ComponentLibrary from '../views/ComponentLibrary/index.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/upload' },
    { path: '/upload', name: 'TenderUpload', component: Upload },
    { path: '/review/:projectId?', name: 'TenderReview', component: Review },
    { path: '/library', name: 'ComponentLibrary', component: ComponentLibrary },
  ],
});

export default router;