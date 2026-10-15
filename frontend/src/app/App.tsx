import { RouterProvider } from 'react-router';
import { router } from './routes';
import { GenerationProgress } from '@/components/GenerationProgress';

export default function App() {
  return (
    <>
      {/* 挂在路由外层：切页面不会中断，生成过程中用户可以去干别的 */}
      <GenerationProgress />
      <RouterProvider router={router} />
    </>
  );
}
