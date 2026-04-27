import { Routes, Route } from 'react-router-dom';
import Home from '../pages/home/Home';
import About from '../pages/about/About';
import Services from '../pages/services/Services';
import NewsPage from '../pages/news/NewsPage';
import NewsItemPage from '../pages/news/NewsItemPage';
import MaterialsPage from '../pages/materials/MaterialsPage';
import MaterialsItemPage from '../pages/materials/MaterialsItemPage';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/about" element={<About />} />
      <Route path="/services" element={<Services />} />
      <Route path="/news" element={<NewsPage />} />
      <Route path="/news/:id" element={<NewsItemPage />} />
      <Route path="/materials" element={<MaterialsPage />} />
      <Route path="/materials/:id" element={<MaterialsItemPage />} />
    </Routes>
  );
}
