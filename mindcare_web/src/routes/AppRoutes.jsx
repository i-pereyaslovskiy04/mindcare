import { Routes, Route } from 'react-router-dom';
import Home from '../pages/Home';
import About from '../pages/About';
import Services from '../pages/Services';
import NewsPage from '../pages/NewsPage';
import NewsItemPage from '../pages/NewsItemPage';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/about" element={<About />} />
      <Route path="/services" element={<Services />} />
      <Route path="/news" element={<NewsPage />} />
      <Route path="/news/:id" element={<NewsItemPage />} />
    </Routes>
  );
}
