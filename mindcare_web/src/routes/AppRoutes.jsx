import { Routes, Route } from 'react-router-dom';
import Home from '../pages/Home';
import NewsPage from '../pages/NewsPage';
import NewsItemPage from '../pages/NewsItemPage';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/news" element={<NewsPage />} />
      <Route path="/news/:id" element={<NewsItemPage />} />
    </Routes>
  );
}
