package org.openjdk.callgraph;

import java.io.BufferedInputStream;
import java.io.BufferedWriter;
import java.io.DataInputStream;
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.MethodModel;
import java.lang.classfile.Opcode;
import java.lang.classfile.attribute.SourceFileAttribute;
import java.lang.classfile.instruction.InvokeDynamicInstruction;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.classfile.instruction.LineNumber;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDesc;
import java.lang.constant.DirectMethodHandleDesc;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Extracts method declarations and bytecode invocation facts from JMOD files. */
public final class MethodGraphExtractor implements AutoCloseable {
    private static final ClassFile CLASS_FILE = ClassFile.of(
            ClassFile.LineNumbersOption.PASS_LINE_NUMBERS);

    private final BufferedWriter methods;
    private final BufferedWriter calls;
    private final BufferedWriter classes;
    private long classCount;
    private long methodCount;
    private long callCount;

    private MethodGraphExtractor(Path outputDirectory) throws IOException {
        Files.createDirectories(outputDirectory);
        methods = writer(outputDirectory.resolve("methods_raw.tsv"));
        calls = writer(outputDirectory.resolve("calls_raw.tsv"));
        classes = writer(outputDirectory.resolve("classes_raw.tsv"));
        methods.write("module_name\tpackage_name\tclass_name\tmethod_name\tdescriptor\taccess_flags\tsource_file\tfirst_line\tlast_line\thas_code\n");
        calls.write("caller_module\tcaller_class\tcaller_name\tcaller_descriptor\tinvoke_kind\tinstruction_ordinal\tsource_line\tdeclared_owner\tdeclared_name\tdeclared_descriptor\tresolution_hint\tbootstrap_owner\tbootstrap_name\n");
        classes.write("module_name\tclass_name\tsuper_name\tinterfaces\taccess_flags\tsource_file\n");
    }

    private static BufferedWriter writer(Path path) throws IOException {
        return Files.newBufferedWriter(path, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: MethodGraphExtractor <jmods-directory> <raw-output-directory>");
            System.exit(2);
        }
        Path jmodsDirectory = Path.of(args[0]);
        if (!Files.isDirectory(jmodsDirectory)) {
            throw new IllegalArgumentException("not a JMOD directory: " + jmodsDirectory);
        }
        List<Path> jmods;
        try (var stream = Files.list(jmodsDirectory)) {
            jmods = stream.filter(path -> path.getFileName().toString().endsWith(".jmod"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .toList();
        }
        if (jmods.isEmpty()) {
            throw new IllegalStateException("no JMOD files found in " + jmodsDirectory);
        }

        try (MethodGraphExtractor extractor = new MethodGraphExtractor(Path.of(args[1]))) {
            for (Path jmod : jmods) {
                extractor.scanJmod(jmod);
                System.err.printf("scanned %s: classes=%d methods=%d calls=%d%n",
                        jmod.getFileName(), extractor.classCount, extractor.methodCount,
                        extractor.callCount);
            }
            System.out.printf("jmods=%d classes=%d methods=%d calls=%d%n",
                    jmods.size(), extractor.classCount, extractor.methodCount,
                    extractor.callCount);
        }
    }

    private void scanJmod(Path jmod) throws IOException {
        String filename = jmod.getFileName().toString();
        String moduleName = filename.substring(0, filename.length() - 5);
        try (DataInputStream input = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(jmod)))) {
            byte[] magic = input.readNBytes(4);
            if (magic.length != 4 || magic[0] != 'J' || magic[1] != 'M') {
                throw new IOException("invalid JMOD header: " + jmod);
            }
            try (ZipInputStream zip = new ZipInputStream(input)) {
                ZipEntry entry;
                while ((entry = zip.getNextEntry()) != null) {
                    String name = entry.getName();
                    if (!entry.isDirectory() && name.startsWith("classes/")
                            && name.endsWith(".class")
                            && !name.startsWith("classes/META-INF/")
                            && !name.equals("classes/module-info.class")) {
                        scanClass(moduleName, CLASS_FILE.parse(zip.readAllBytes()));
                    }
                    zip.closeEntry();
                }
            }
        }
    }

    private void scanClass(String moduleName, ClassModel model) throws IOException {
        String className = model.thisClass().asInternalName();
        String superName = model.superclass().map(entry -> entry.asInternalName()).orElse("");
        String interfaces = String.join(",", model.interfaces().stream()
                .map(entry -> entry.asInternalName()).toList());
        String sourceFile = model.attributes().stream()
                .filter(SourceFileAttribute.class::isInstance)
                .map(SourceFileAttribute.class::cast)
                .map(attribute -> attribute.sourceFile().stringValue())
                .findFirst().orElse("");
        classes.write(row(moduleName, className, superName, interfaces,
                Integer.toString(model.flags().flagsMask()), sourceFile));
        classes.newLine();
        classCount++;
        for (MethodModel method : model.methods()) {
            scanMethod(moduleName, className, sourceFile, method);
        }
    }

    private void scanMethod(String moduleName, String className, String sourceFile,
                            MethodModel method) throws IOException {
        String name = method.methodName().stringValue();
        String descriptor = method.methodType().stringValue();
        int firstLine = -1;
        int lastLine = -1;
        boolean hasCode = method.code().isPresent();
        if (hasCode) {
            for (CodeElement element : method.code().orElseThrow()) {
                if (element instanceof LineNumber line) {
                    firstLine = firstLine < 0 ? line.line() : Math.min(firstLine, line.line());
                    lastLine = Math.max(lastLine, line.line());
                }
            }
        }
        methods.write(row(moduleName, packageName(className), className, name, descriptor,
                Integer.toString(method.flags().flagsMask()), sourceFile,
                nullableInt(firstLine), nullableInt(lastLine), Boolean.toString(hasCode)));
        methods.newLine();
        methodCount++;
        if (hasCode) {
            scanCode(moduleName, className, name, descriptor, method.code().orElseThrow());
        }
    }

    private void scanCode(String moduleName, String className, String methodName,
                          String methodDescriptor, CodeModel code) throws IOException {
        int currentLine = -1;
        int invokeOrdinal = 0;
        for (CodeElement element : code) {
            if (element instanceof LineNumber line) {
                currentLine = line.line();
            } else if (element instanceof InvokeInstruction invoke) {
                emitCall(moduleName, className, methodName, methodDescriptor,
                        invokeKind(invoke.opcode()), invokeOrdinal++, currentLine,
                        invoke.owner().asInternalName(), invoke.name().stringValue(),
                        invoke.type().stringValue(), "DECLARED", "", "");
            } else if (element instanceof InvokeDynamicInstruction dynamic) {
                DirectMethodHandleDesc bootstrap = dynamic.bootstrapMethod();
                boolean emitted = false;
                for (ConstantDesc argument : dynamic.bootstrapArgs()) {
                    if (argument instanceof DirectMethodHandleDesc handle && isMethodHandle(handle)) {
                        emitCall(moduleName, className, methodName, methodDescriptor, "DYNAMIC",
                                invokeOrdinal++, currentLine, internalName(handle.owner()),
                                handle.methodName(), handle.lookupDescriptor(), "BOOTSTRAP_HANDLE",
                                internalName(bootstrap.owner()), bootstrap.methodName());
                        emitted = true;
                    }
                }
                if (!emitted) {
                    emitCall(moduleName, className, methodName, methodDescriptor, "DYNAMIC",
                            invokeOrdinal++, currentLine, "", dynamic.name().stringValue(),
                            dynamic.type().stringValue(), "UNRESOLVED_DYNAMIC",
                            internalName(bootstrap.owner()), bootstrap.methodName());
                }
            }
        }
    }

    private void emitCall(String callerModule, String callerClass, String callerName,
                          String callerDescriptor, String kind, int ordinal, int line,
                          String owner, String name, String descriptor, String hint,
                          String bootstrapOwner, String bootstrapName) throws IOException {
        calls.write(row(callerModule, callerClass, callerName, callerDescriptor, kind,
                Integer.toString(ordinal), nullableInt(line), owner, name, descriptor, hint,
                bootstrapOwner, bootstrapName));
        calls.newLine();
        callCount++;
    }

    private static String invokeKind(Opcode opcode) {
        return switch (opcode) {
            case INVOKESTATIC -> "STATIC";
            case INVOKESPECIAL -> "SPECIAL";
            case INVOKEVIRTUAL -> "VIRTUAL";
            case INVOKEINTERFACE -> "INTERFACE";
            default -> throw new IllegalArgumentException("unexpected invoke opcode: " + opcode);
        };
    }

    private static boolean isMethodHandle(DirectMethodHandleDesc handle) {
        return switch (handle.kind()) {
            case STATIC, INTERFACE_STATIC, VIRTUAL, INTERFACE_VIRTUAL, SPECIAL,
                    INTERFACE_SPECIAL, CONSTRUCTOR -> true;
            default -> false;
        };
    }

    private static String internalName(ClassDesc descriptor) {
        String value = descriptor.descriptorString();
        return value.startsWith("L") && value.endsWith(";")
                ? value.substring(1, value.length() - 1) : value;
    }

    private static String packageName(String internalClassName) {
        int separator = internalClassName.lastIndexOf('/');
        return separator < 0 ? "" : internalClassName.substring(0, separator).replace('/', '.');
    }

    private static String nullableInt(int value) {
        return value < 0 ? "" : Integer.toString(value);
    }

    private static String row(String... values) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < values.length; index++) {
            if (index > 0) result.append('\t');
            result.append(escape(values[index]));
        }
        return result.toString();
    }

    private static String escape(String value) {
        if (value == null || value.isEmpty()) return "";
        return value.replace("\\", "\\\\").replace("\t", "\\t")
                .replace("\r", "\\r").replace("\n", "\\n");
    }

    @Override
    public void close() throws IOException {
        methods.close();
        calls.close();
        classes.close();
    }
}
