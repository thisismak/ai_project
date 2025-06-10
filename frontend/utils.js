async function apiRequest(url, method, data) {
  const token = localStorage.getItem('token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };

  try {
    const response = await fetch(url, {
      method,
      headers,
      ...(data && method !== 'GET' && { body: JSON.stringify(data) }),
    });
    return await response.json();
  } catch (error) {
    console.error('API 請求失敗:', error);
    throw error;
  }
}