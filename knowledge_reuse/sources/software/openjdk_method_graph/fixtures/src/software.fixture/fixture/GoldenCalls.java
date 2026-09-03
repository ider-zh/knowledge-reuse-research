package fixture;

public final class GoldenCalls {
    interface Worker {
        void run();
    }

    abstract static class NativeBoundary {
        abstract void abstractCall();

        native void nativeCall();
    }

    private GoldenCalls() {}

    static void staticTarget() {}

    void virtualTarget() {}

    void exercise(Worker worker) {
        staticTarget();
        virtualTarget();
        worker.run();
        Runnable lambda = GoldenCalls::staticTarget;
        lambda.run();
        new GoldenCalls();
    }
}
