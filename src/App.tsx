import Agent from "./components/Agent";
import { ErrorBoundary } from "./components/ErrorBoundary";

function App() {
  return (
    <div className="w-full h-full bg-transparent flex items-center justify-center">
      <ErrorBoundary>
        <Agent wsUrl="ws://localhost:8765/ws" />
      </ErrorBoundary>
    </div>
  );
}

export default App;
