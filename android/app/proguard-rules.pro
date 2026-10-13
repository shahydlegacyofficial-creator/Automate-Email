# JavaMail / activation use reflection and service files.
-keep class com.sun.mail.** { *; }
-keep class javax.mail.** { *; }
-keep class javax.activation.** { *; }
-keep class com.sun.activation.** { *; }
-keep class myjava.awt.datatransfer.** { *; }
-dontwarn java.awt.**
-dontwarn java.beans.**
-dontwarn javax.naming.**
-dontwarn javax.security.**
-dontwarn org.ietf.jgss.**
-dontwarn sun.security.**
-dontwarn com.sun.mail.**
-dontwarn javax.activation.**

# The WebView editor calls back into Kotlin through @JavascriptInterface methods.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface

# Our serializable models.
-keep,includedescriptorclasses class com.travelessence.emailstudio.core.**$$serializer { *; }
-keepclassmembers class com.travelessence.emailstudio.core.** {
    *** Companion;
}
-keepclasseswithmembers class com.travelessence.emailstudio.core.** {
    kotlinx.serialization.KSerializer serializer(...);
}
