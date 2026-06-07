import Agent from "./components/Agent";

function App() {
  return (
    <div className="w-full h-full bg-transparent flex items-center justify-center">
      <Agent wsUrl="ws://localhost:8765/ws" />
    </div>
  );
}

export default App;
